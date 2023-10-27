from typing import Optional

import chainlit as cl

# @cl.header_auth_callback
# def header_auth_callback(headers) -> Optional[cl.AppUser]:
#   # Verify the signature of a token in the header (ex: jwt token)
#   # or check that the value is matching a row from your database
#   if headers.get("test-header") == "test-value":
#     return cl.AppUser(username="admin", role="ADMIN", provider="header")
#   else:
#     return None
  
@cl.password_auth_callback
def auth_callback(username: str, password: str) -> Optional[cl.AppUser]:
  # Fetch the user matching username from your database
  # and compare the hashed password with the value stored in the database
  if (username, password) == ("admin", "admin"):
    return cl.AppUser(username="admin", role="ADMIN", provider="credentials")
  else:
    return None

@cl.author_rename
def rename(orig_author: str):
    rename_dict = {"Chatbot": "Botanica"}
    return rename_dict.get(orig_author, orig_author)

@cl.action_callback("action_button")
async def on_action(action):
    await cl.Message(content=f"Executed {action.name}").send()
    # Optionally remove the action button from the chatbot user interface
    await action.remove()

@cl.on_message
async def start():
    # Sending an action button within a chatbot message
    actions = [
        cl.Action(name="action_button", value="example_value", description="Click me!")
    ]

    await cl.Message(content="Interact with this action button:", actions=actions).send()

@cl.on_message
async def main(message: cl.Message):
    # Your custom logic goes here...

    # Send a response back to the user
    await cl.Message(
        content=f"Received: {message.content}",
    ).send()

# @cl.oauth_callback
# def auth_callback(provider_id: str, token: str, raw_user_data, default_app_user):
#     if provider_id == "google":
#         if "@icloud.com" in raw_user_data["email"]:
#             return default_app_user
#         return None
