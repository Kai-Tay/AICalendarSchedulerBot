import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
import os

# Load environment variables
load_dotenv()

# Initialize LangChain model
model = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash", 
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.2
)

# Initialize Google Calendar API
creds = service_account.Credentials.from_service_account_file(
    'service-account.json',
    scopes=['https://www.googleapis.com/auth/calendar']
)
calendar_service = build('calendar', 'v3', credentials=creds)
calendar_id = os.getenv("CALENDER_ID")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

# Tools
@tool
def get_current_date():
    """Get the current date and time in Singapore"""
    # Get current date in Singapore, run this every time
    current_date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")
    current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%H:%M")
    return f"Current date: {current_date}, Current time: {current_time}"

@tool
def get_events():
    """Get all events from the calendar to ensure that the date is available before adding/deleting/rescheduling events"""
    try:
        # Get current time in ISO format for filtering future events
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
        # Get future events from the calendar
        events = calendar_service.events().list(
            calendarId=calendar_id,
            timeMin=now,  # Only get events from now onwards
            maxResults=50,  # Limit to 50 events
            singleEvents=True,  # Expand recurring events
            orderBy='startTime'  # Order by start time
        ).execute()

        # Format the events for the AI
        if 'items' in events and events['items']:
            event_list = []
            for event in events['items']:
                summary = event.get('summary', 'No title')
                start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', 'No date'))
                id = event.get('id', 'No id')
                event_list.append(f"- {summary} on {start}, event_id: {id}")
            return f"Upcoming events:\n" + "\n".join(event_list)
        else:
            return "No upcoming events found."
    except Exception as e:
        print(f"Error getting events: {e}")
        return f"Error accessing calendar: {e}"

@tool
def add_event(date: str, time: str, duration: float, description: str):
    """Add a new event to the calendar, calculate end time based off duration.
    
    Args:
        date: The date of the event (YYYY-MM-DD format)
        time: The time of the event (HH:MM format)
        duration: The duration of the event (in minutes)
        description: Description of the event
    """
    try:
        # Calculate end time
        end_time = datetime.datetime.strptime(time, "%H:%M") + datetime.timedelta(minutes=duration)

        # Call Google Calendar API to add an event
        event = calendar_service.events().insert(
            calendarId=calendar_id,
            body={
                'summary': description,
                'start': {'dateTime': f'{date}T{time}:00+08:00'},
                'end': {'dateTime': f'{date}T{end_time.strftime("%H:%M")}:00+08:00'}
            }
        ).execute()
        return f"Event '{description}' added successfully on {date} at {time} for {duration} minutes"
    except Exception as e:
        return f"Error adding event: {e}"

@tool
def remove_event(event_id: str):
    """Remove an event from the calendar
    
    Args:
        event_id: The ID of the event to remove
    """
    try:
        # Call Google Calendar API to remove an event
        calendar_service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return f"Event with ID {event_id} removed successfully"
    except Exception as e:
        return f"Error removing event: {e}"

@tool
def reschedule_event(event_id: str, new_date: str, new_time: str, new_duration: float):
    """Reschedule an existing event
    
    Args:
        event_id: The ID of the event to reschedule
        new_date: The new date for the event (YYYY-MM-DD format)
        new_time: The new time for the event (HH:MM format)
        new_duration: The new duration for the event (in minutes)
    """
    try:
        # Calculate end time
        new_end_time = datetime.datetime.strptime(new_time, "%H:%M") + datetime.timedelta(minutes=new_duration)

        # Get the existing event to preserve its summary
        existing_event = calendar_service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        # Call Google Calendar API to reschedule an event
        calendar_service.events().update(calendarId=calendar_id, eventId=event_id, body={
                'summary': existing_event.get('summary', 'Rescheduled Event'),
                'start': {'dateTime': f'{new_date}T{new_time}:00+08:00'},
                'end': {'dateTime': f'{new_date}T{new_end_time.strftime("%H:%M")}:00+08:00'}
            }).execute()
        return f"Event '{existing_event.get('summary', 'Rescheduled Event')}' rescheduled to {new_date} at {new_time} for {new_duration} minutes"
    except Exception as e:
        return f"Error rescheduling event: {e}"

instructions = f"""
                You are a helpful calendar scheduler. You are given a event date and you need to check if the date is available. 
                Use the tools to call Google Calendar API to check if the date is available on my calendar. 
                ALWAYS call the get_current_date tool before calling the other tools.

                If it clashes with another event, you need to ask me if I would like to schedule it on a different date or change the current date or just add it to the calendar.

                Tools:
                - get_current_date: Get the current date and time in Singapore
                - get_events: Get all events from the calendar to ensure that the date is available before adding/deleting/rescheduling events
                - add_event: Add a new event to the calendar
                - remove_event: Remove an event from the calendar
                - reschedule_event: Reschedule an existing event
                
                If it is, help me schedule the event.
                If it is not, you need to tell me that the date is not available, and if I would like to schedule it on a different date or change the current date.
                If I am rescheduling the event, you need to ask me for the new date and time.
                """

# Bind tools to the model
tools_list = [get_current_date, get_events, add_event, remove_event, reschedule_event]
model_with_tools = model.bind_tools(tools_list)

async def schedule_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != 716853175:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You are not Kai Sheng.. wya doing here.... 😡")
        return

    # Get user message
    user_message = update.message.text
    
    # Initialize conversation history if not exists
    if 'messages' not in context.user_data:
        context.user_data['messages'] = [SystemMessage(content=instructions)]
    
    # Add user message to history
    context.user_data['messages'].append(HumanMessage(content=user_message))

    try:
        # Generate response with tools
        response = model_with_tools.invoke(context.user_data['messages'])
        
        # Handle tool calls if present
        while response.tool_calls:
            # Add AI message with tool calls to history
            context.user_data['messages'].append(response)
            
            # Execute each tool call
            for tool_call in response.tool_calls:
                tool_name = tool_call['name']
                tool_args = tool_call['args']
                
                # Find and execute the tool
                tool_result = None
                for tool in tools_list:
                    if tool.name == tool_name:
                        try:
                            if tool_name == "get_current_date":
                                tool_result = tool.invoke({})
                            elif tool_name == "get_events":
                                tool_result = tool.invoke({})
                            elif tool_name == "add_event":
                                tool_result = tool.invoke(tool_args)
                            elif tool_name == "remove_event":
                                tool_result = tool.invoke(tool_args)
                            elif tool_name == "reschedule_event":
                                tool_result = tool.invoke(tool_args)
                        except Exception as e:
                            tool_result = f"Error executing {tool_name}: {str(e)}"
                        break
                
                if tool_result is None:
                    tool_result = f"Unknown tool: {tool_name}"
                
                # Add tool result to messages
                context.user_data['messages'].append(
                    ToolMessage(content=str(tool_result), tool_call_id=tool_call['id'])
                )
            
            # Get next response from model
            response = model_with_tools.invoke(context.user_data['messages'])
        
        # Add final AI response to history
        context.user_data['messages'].append(response)
        
        # Send response to user
        assistant_reply = response.content
        if not assistant_reply or assistant_reply.strip() == "":
            assistant_reply = "I'm sorry, I couldn't generate a response. Please try again."
        
        await update.message.reply_text(assistant_reply)
        
    except Exception as e:
        print(f"Error in schedule_event: {e}")
        await update.message.reply_text("Sorry, I encountered an error. Please try again.")

def main():

    application = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    
    # Message handlers
    schedule_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_event)
    application.add_handler(schedule_handler)

    # Polls every 5 seconds
    application.run_polling(poll_interval=5.0)

if __name__ == '__main__':
    main()