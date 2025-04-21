import re
import os
import urllib.parse
import chainlit as cl
from typing import List
from dotenv import load_dotenv
from google.api_core.client_options import ClientOptions
from google.cloud import discoveryengine_v1 as discoveryengine

# Set up logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
PROJECT_ID = os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("LOCATION", "global")  # Values: "global", "us", "eu"
DATA_STORE_ID = os.environ.get("DATA_STORE_ID")

# Log configuration
logger.info(f"Starting application with:")
logger.info(f"PROJECT_ID: {'Set' if PROJECT_ID else 'Not set'}")
logger.info(f"LOCATION: {LOCATION}")
logger.info(f"DATA_STORE_ID: {'Set' if DATA_STORE_ID else 'Not set'}")

# Validate configuration
if not all([PROJECT_ID, DATA_STORE_ID]):
    logger.error("Missing required environment variables")
    raise ValueError("Missing required environment variables. Please check .env file.")

def parse_external_link(url=''):
    """Convert GCS URLs to public URLs without encoding."""
    if not url:
        return url
        
    # Convert GCS URLs to public URLs
    protocol_regex = r'^(gs)://'
    match = re.match(protocol_regex, url)
    protocol = match.group(1) if match else None

    if protocol == 'gs':
        url = re.sub(protocol_regex, 'https://storage.cloud.google.com/', url)
    
    return url

def format_citations(text: str, urls: List) -> str:
    """Format citations with numbered references and list URLs at the end."""
    # Track references and their URLs
    references = {}
    reference_counter = 1
    
    # Split text into parts using '[' and ']'
    parts = text.split('[')
    
    # Initialize the formatted text
    formatted_text = parts[0]
    
    # Iterate through the remaining parts
    for part in parts[1:]:
        # Check if the part contains a reference
        if ']' in part:
            # Extract the reference number
            reference_str = part.split(']')[0]
            try:
                ref_numbers = [int(ref.strip()) for ref in reference_str.split(',')]
                
                # Create numbered citations
                citation_numbers = []
                for ref_num in ref_numbers:
                    if ref_num <= len(urls) and ref_num > 0:
                        # Get the URL
                        url = parse_external_link(urls[ref_num - 1].uri)
                        
                        # If this URL is not already referenced, add it
                        if url not in references.values():
                            references[reference_counter] = url
                            citation_numbers.append(str(reference_counter))
                            reference_counter += 1
                        else:
                            # Find the existing reference number for this URL
                            for ref_id, ref_url in references.items():
                                if ref_url == url:
                                    citation_numbers.append(str(ref_id))
                                    break
                
                # Replace with numbered citation
                if citation_numbers:
                    formatted_text += '[' + ', '.join(citation_numbers) + ']' + part.split(']')[1]
                else:
                    formatted_text += '[' + reference_str + ']' + part.split(']')[1]
            except ValueError:
                # If reference is not a number, keep original text
                formatted_text += '[' + part
        else:
            formatted_text += '[' + part  # Re-attach if no reference
    
    # Add references list at the end if there are any
    if references:
        formatted_text += "\n\n**References:**\n"
        for ref_id, url in references.items():
            # Encode URL for markdown
            encoded_url = urllib.parse.quote(url, safe=':/')
            formatted_text += f"[{ref_id}] {encoded_url}\n"
    
    return formatted_text

def initialize_client():
    """Initialize the Discovery Engine client."""
    logger.info("Initializing Discovery Engine client")
    # Set API endpoint based on location
    client_options = (
        ClientOptions(api_endpoint=f"{LOCATION}-discoveryengine.googleapis.com")
        if LOCATION != "global"
        else None
    )
    # Create a client
    client = discoveryengine.ConversationalSearchServiceClient(
        client_options=client_options
    )
    logger.info("Discovery Engine client initialized successfully")
    return client

def initialize_conversation(client):
    """Create a new conversation instance."""
    logger.info("Creating new conversation")
    parent_path = client.data_store_path(
        project=PROJECT_ID, location=LOCATION, data_store=DATA_STORE_ID
    )
    logger.info(f"Using parent path: {parent_path}")
    
    conversation_instance = client.create_conversation(
        # The full resource name of the data store
        parent=parent_path,
        conversation=discoveryengine.Conversation(),
    )
    logger.info(f"Conversation created with name: {conversation_instance.name}")
    return conversation_instance

# Initialize the client
logger.info("Initializing global client")
discoveryengine_client = initialize_client()
logger.info("Global client initialized")

# Add a global variable to store the conversation name as a fallback
GLOBAL_CONVERSATION_NAME = None

@cl.on_chat_start
async def on_chat_start():
    """Initialize the conversation when a new chat starts."""
    global GLOBAL_CONVERSATION_NAME
    logger.info("Chat started, initializing conversation")
    try:
        # Initialize the conversation
        conversation = initialize_conversation(discoveryengine_client)
        
        # Store the conversation name in both the session and global variable
        GLOBAL_CONVERSATION_NAME = conversation.name
        logger.info(f"Setting global conversation name: {GLOBAL_CONVERSATION_NAME}")
        
        cl.user_session.set("conversation", conversation.name)
        logger.info("Conversation name stored in user session")
        
        await cl.Message(
            content="Welcome to the Document Search Assistant. How can I help you today?",
            type="system"
        ).send()
        logger.info("Welcome message sent")
    except Exception as e:
        logger.error(f"Error initializing conversation: {str(e)}", exc_info=True)
        error_message = f"Failed to initialize conversation: {str(e)}"
        await cl.Message(content=error_message, type="error").send()

# Source action callbacks removed as requested

@cl.action_callback("new_conversation")
async def on_new_conversation(action):
    """Start a new conversation when requested."""
    global GLOBAL_CONVERSATION_NAME
    # No need to access action.payload here as we don't need any specific value
    try:
        conversation = initialize_conversation(discoveryengine_client)
        # Store in both session and global variable
        GLOBAL_CONVERSATION_NAME = conversation.name
        cl.user_session.set("conversation", conversation.name)
        await cl.Message(
            content="Started a new conversation. What would you like to search for?",
            type="system"
        ).send()
    except Exception as e:
        error_message = f"Failed to start new conversation: {str(e)}"
        await cl.Message(content=error_message, type="error").send()

@cl.on_message
async def on_message(message: cl.Message):
    """Process user messages and return search results."""
    global GLOBAL_CONVERSATION_NAME
    logger.info(f"Received message: {message.content}")
    
    # Try to get conversation name from session, fall back to global variable
    conversation_name = cl.user_session.get("conversation")
    logger.info(f"Conversation name from session: {conversation_name}")
    
    if not conversation_name:
        logger.info(f"Using global conversation name: {GLOBAL_CONVERSATION_NAME}")
        conversation_name = GLOBAL_CONVERSATION_NAME
    
    # If still no conversation name, try to create a new conversation
    if not conversation_name:
        logger.warning("No conversation name found, creating new conversation")
        try:
            conversation = initialize_conversation(discoveryengine_client)
            conversation_name = conversation.name
            GLOBAL_CONVERSATION_NAME = conversation_name
            logger.info(f"Created new conversation: {conversation_name}")
            cl.user_session.set("conversation", conversation_name)
            logger.info("Stored new conversation in session")
        except Exception as e:
            logger.error(f"Failed to create new conversation: {str(e)}", exc_info=True)
            await cl.Message(
                content=f"Failed to initialize conversation: {str(e)}",
                type="error"
            ).send()
            return
    
    try:
        # Create search request
        request = discoveryengine.ConverseConversationRequest(
            name=conversation_name,
            query=discoveryengine.TextInput(input=message.content),
            serving_config=discoveryengine_client.serving_config_path(
                project=PROJECT_ID,
                location=LOCATION,
                data_store=DATA_STORE_ID,
                serving_config="default_config",
            ),
            # Options for the returned summary
            summary_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                # Number of results to include in summary
                summary_result_count=3,
                model_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec.ModelSpec(
                    version="gemini-1.5-flash-001/answer_gen/v1"
                ),
                model_prompt_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec.ModelPromptSpec(
                    preamble="Given the conversation between a user and a helpful assistant and some search results, "
                            "create a final answer for the assistant. Always respond back to the user in the same "
                            "language as the user. The answer should use all relevant information from the search "
                            "results, not introduce any additional information, and use exactly the same words as "
                            "the search results when possible. The assistant's answer should be formatted as a bulleted list."
                ),
                include_citations=True,
            ),
        )
        
        # Execute search
        response = discoveryengine_client.converse_conversation(request)
        
        # Process response
        try:
            # Try to get response with formatted citations
            content = format_citations(
                response.reply.summary.summary_text,
                response.reply.summary.summary_with_metadata.references
            )
            
            # Source buttons removed as requested
            actions = []
        except AttributeError:
            # Fallback to basic response if no citations
            content = response.reply.summary.summary_text
            actions = []
        
        # Add new conversation action
        actions.append(
            cl.Action(
                name="new_conversation",
                label="New Conversation",
                value="new_conversation",
                payload={"action": "new_conversation"}
            )
        )
        
        # Send response
        await cl.Message(content=content, actions=actions).send()
        
    except Exception as e:
        error_message = f"Search failed: {str(e)}"
        await cl.Message(content=error_message, type="error").send()

if __name__ == "__main__":
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)
