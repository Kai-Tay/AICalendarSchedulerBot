import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv
import requests
from google import genai
from google.genai import types
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime

import os

# Load environment variables
load_dotenv()

# Initialize Google Calendar API
creds = service_account.Credentials.from_service_account_file(
    'service-account.json',
    scopes=['https://www.googleapis.com/auth/calendar']
)
calendar_service = build('calendar', 'v3', credentials=creds)
calendar_id = os.getenv("CALENDER_ID")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Initialize Gemini
gemini = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# Tools
def get_current_date():
    # Get current date in Singapore, run this every time
    current_date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")
    current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%H:%M")
    return current_date, current_time

def get_events():
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
                event_list.append(f"- {summary} on {start}")

            return f"Upcoming events:\n" + "\n".join(event_list)
    except Exception as e:
        print(f"Error getting events: {e}")
        return f"Error accessing calendar: {str(e)}"

def add_event(date: str, time: str, description: str):
    # Call Google Calendar API to add an event
    event = calendar_service.events().insert(
        calendarId=calendar_id,
        body={
            'summary': description,
            'start': {'dateTime': f'{date}T{time}:00+08:00'},
            'end': {'dateTime': f'{date}T{time}:00+08:00'}
        }
    ).execute()
    # Return the event
    return "Event added"

def remove_event(event_id: str):
    # Call Google Calendar API to remove an event
    # Return the event
    return "Event removed"

def reschedule_event(event_id: str, new_date: str, new_time: str):
    # Call Google Calendar API to reschedule an event
    # Return the event
    return "Event rescheduled"

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

# Define function schemas for Gemini tools
function_declarations = [
    {
        "name": "get_current_date",
        "description": "Get the current date and time in Singapore",
        "parameters": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "get_events",
        "description": "Get all events from the calendar to ensure that the date is available before adding/deleting/rescheduling events",
        "parameters": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "add_event",
        "description": "Add a new event to the calendar",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "The date of the event (YYYY-MM-DD format)"
                },
                "time": {
                    "type": "string", 
                    "description": "The time of the event (HH:MM format)"
                },
                "description": {
                    "type": "string",
                    "description": "Description of the event"
                }
            },
            "required": ["date", "time", "description"]
        }
    },
    {
        "name": "remove_event",
        "description": "Remove an event from the calendar",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "The ID of the event to remove"
                }
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "reschedule_event",
        "description": "Reschedule an existing event",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "The ID of the event to reschedule"
                },
                "new_date": {
                    "type": "string",
                    "description": "The new date for the event (YYYY-MM-DD format)"
                },
                "new_time": {
                    "type": "string",
                    "description": "The new time for the event (HH:MM format)"
                }
            },
            "required": ["event_id", "new_date", "new_time"]
        }
    }
]

tools = types.Tool(function_declarations=function_declarations)
config = types.GenerateContentConfig(tools=[tools], system_instruction=instructions)

async def schedule_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != 716853175:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You are not Kai Sheng.. wya doing here.... 😡")

    # Get user message
    user_message = update.message.text
    context.user_data.setdefault('history', []).append({"role": "user", "parts": [{"text": user_message}]})

    # Generate response
    response = gemini.models.generate_content(
            model="gemini-2.0-flash",
            contents=context.user_data['history'],
            config=config
        )
    
    assistant = response.text
    
    # Handle function calls if present
    if response.candidates and response.candidates[0].content.parts:
        parts = response.candidates[0].content.parts
        function_calls = []
        text_parts = []
        print("Parts")
        print(parts)
        for part in parts:
            if hasattr(part, 'function_call') and part.function_call is not None:
                function_calls.append(part.function_call)
            if hasattr(part, 'text') and part.text is not None:
                text_parts.append(part.text)
                
        print("Function calls", function_calls)
        print("Text parts", text_parts)
        # Execute function calls
        if function_calls:
            for func_call in function_calls:
                func_name = func_call.name
                args = func_call.args
                print(f"Function name: {func_name}, args: {args}")
                
                if func_name == "get_current_date":
                    current_date, current_time = get_current_date()
                    result = f"Current date: {current_date}, Current time: {current_time}"
                elif func_name == "get_events":
                    result = get_events()
                elif func_name == "add_event":
                    result = add_event(args.get("date"), args.get("time"), args.get("description"))
                elif func_name == "remove_event":
                    result = remove_event(args.get("event_id"))
                elif func_name == "reschedule_event":
                    result = reschedule_event(args.get("event_id"), args.get("new_date"), args.get("new_time"))
                else:
                    result = "Unknown function"
                
                # Add function result to history
                context.user_data['history'].append({
                    "role": "model",
                    "parts": [{"text": result}]
                })
            print("History", context.user_data['history'])
            
            # Keep calling Gemini until it stops calling functions
            max_iterations = 5  # Prevent infinite loops
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                print(f"Function call iteration {iteration}")
                
                # Make another API call to get Gemini's response after function execution
                response = gemini.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=context.user_data['history'],
                    config=config
                )
                
                # Check if there are more function calls
                if response.candidates and response.candidates[0].content.parts:
                    parts = response.candidates[0].content.parts
                    new_function_calls = []
                    new_text_parts = []
                    
                    for part in parts:
                        if hasattr(part, 'function_call') and part.function_call is not None:
                            new_function_calls.append(part.function_call)
                        if hasattr(part, 'text') and part.text is not None:
                            new_text_parts.append(part.text)
                    
                    print(f"New function calls: {new_function_calls}")
                    print(f"New text parts: {new_text_parts}")
                    
                    if new_function_calls:
                        # Execute the new function calls
                        for func_call in new_function_calls:
                            func_name = func_call.name
                            args = func_call.args
                            print(f"Executing function: {func_name}, args: {args}")
                            
                            if func_name == "get_current_date":
                                current_date, current_time = get_current_date()
                                result = f"Current date: {current_date}, Current time: {current_time}"
                            elif func_name == "get_events":
                                result = get_events()
                            elif func_name == "add_event":
                                result = add_event(args.get("date"), args.get("time"), args.get("description"))
                            elif func_name == "remove_event":
                                result = remove_event(args.get("event_id"))
                            elif func_name == "reschedule_event":
                                result = reschedule_event(args.get("event_id"), args.get("new_date"), args.get("new_time"))
                            else:
                                result = "Unknown function"
                            
                            # Add function result to history
                            context.user_data['history'].append({
                                "role": "model",
                                "parts": [{"text": result}]
                            })
                        # Continue the loop to check for more function calls
                    else:
                        # No more function calls, we have the final response
                        assistant = " ".join(new_text_parts) if new_text_parts else response.text
                        break
                else:
                    # No valid response parts
                    assistant = response.text
                    break
            
            if iteration >= max_iterations:
                print("Max iterations reached, stopping function call loop")
                assistant = "I've processed your request, but it took longer than expected."
    
    if not assistant or assistant.strip() == "":
        assistant = "I'm sorry, I couldn't generate a response. Please try again."
    
    context.user_data['history'].append({"role": "assistant", "parts": [{"text": assistant}]})

    # Send response
    await update.message.reply_text(assistant)
        

def main():

    application = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    
    # Message handlers
    schedule_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_event)
    application.add_handler(schedule_handler)

    application.run_polling(poll_interval=5.0)

if __name__ == '__main__':
    main()