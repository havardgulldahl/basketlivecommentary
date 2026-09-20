Python API

This project uses the Python API from [Datasette `llm`](https://llm.datasette.io/)
to generate live commentary. The default model is the GPT4All model
`qwen2-1_5b-instruct-q4_0`.

## Project setup

Install the CLI and the GPT4All plugin in the `uv` tool environment:

```console
uv tool install llm
llm install llm-gpt4all
```

The project dependencies also include both packages, so `uv sync` makes the
same API and plugin available to `uv run`:

```console
uv sync
uv run llm models list
```

The GPT4All plugin downloads the roughly 894 MB model automatically when it is
first used and stores it in its local model cache.

## Application usage

The application follows the standard `llm` Python API:

```python
import llm

model = llm.get_model("qwen2-1_5b-instruct-q4_0")
response = model.prompt(
    "Generate one short live basketball commentary sentence.",
    system="You are a concise live basketball commentator.",
)
print(response.text())
```

`src/llm_commentary.py` serializes a short batch of normalized match events as
JSON, sends it through this API, and falls back to deterministic commentary if
the model cannot be initialized or a request fails.

## Generic API reference

Understanding this API is also important for writing Plugins.

Basic prompt execution
To run a prompt against a configured model, run this:

import llm

model = llm.get_model("qwen2-1_5b-instruct-q4_0")
response = model.prompt("Five surprising names for a pet pelican")
print(response.text())
Note that the prompt will not be evaluated until you call that response.text() method - a form of lazy loading.

If you inspect the response before it has been evaluated it will look like this:

<Response prompt='Your prompt' text='... not yet done ...'>
The llm.get_model() function accepts model IDs or aliases. You can also omit it
to use the currently configured default model.

For remote models, credentials can be configured using the provider's
environment variable or the `llm keys set` command. GPT4All runs locally and
does not require an API key.

The __str__() method of response also returns the text of the response, so you can do this instead:

print(llm.get_model().prompt("Five surprising names for a pet pelican"))
You can run this command to see a list of available models and their aliases:

llm models
If you have set a OPENAI_API_KEY environment variable you can omit the model.key = line.

Calling llm.get_model() with an invalid model ID will raise a llm.UnknownModelError exception.

System prompts
For models that accept a system prompt, pass it as system="...":

response = model.prompt(
    "Five surprising names for a pet pelican",
    system="Answer like GlaDOS"
)
Attachments
Models that accept multi-modal input (images, audio, video etc) can be passed attachments using the attachments= keyword argument. This accepts a list of llm.Attachment() instances.

This example shows two attachments - one from a file path and one from a URL:

import llm

model = llm.get_model("qwen2-1_5b-instruct-q4_0")
response = model.prompt(
    "Describe these images",
    attachments=[
        llm.Attachment(path="pelican.jpg"),
        llm.Attachment(url="https://static.simonwillison.net/static/2024/pelicans.jpg"),
    ]
)
Use llm.Attachment(content=b"binary image content here") to pass binary content directly.

class llm.Attachment(type: str | None = None, path: str | None = None, url: str | None = None, content: bytes | None = None, _id: str | None = None)
An attachment (image, audio, etc) to include with a prompt.

base64_content()
Return the content as a base64-encoded string.

content_bytes()
Return the binary content, reading from path or URL if needed.

resolve_type()
Return the content type, guessing from content if not specified.

You can check which attachment types (if any) a model supports using the model.attachment_types set:

model = llm.get_model("qwen2-1_5b-instruct-q4_0")
print(model.attachment_types)
# {'image/gif', 'image/png', 'image/jpeg', 'image/webp'}

if "image/jpeg" in model.attachment_types:
    # Use a JPEG attachment here
    ...


Schemas
As with the CLI tool some models support passing a JSON schema should be used for the resulting response.

You can pass this to the prompt(schema=) parameter as either a Python dictionary or a Pydantic BaseModel subclass:

import llm, json
from pydantic import BaseModel

class Dog(BaseModel):
    name: str
    age: int

model = llm.get_model("qwen2-1_5b-instruct-q4_0")
response = model.prompt("Describe a nice dog", schema=Dog)
dog = json.loads(response.text())
print(dog)
# {"name":"Buddy","age":3}
You can also pass a schema directly, like this:

response = model.prompt("Describe a nice dog", schema={
    "properties": {
        "name": {"title": "Name", "type": "string"},
        "age": {"title": "Age", "type": "integer"},
    },
    "required": ["name", "age"],
    "title": "Dog",
    "type": "object",
})


Passing an API key
Models that accept API keys should take an additional key= parameter to their model.prompt() method:

model = llm.get_model("qwen2-1_5b-instruct-q4_0")
print(model.prompt("Names for beavers", key="sk-..."))
If you don’t provide this argument LLM will attempt to find it from an environment variable (OPENAI_API_KEY for OpenAI, others for different plugins) or from keys that have been saved using the llm keys set command.

Some model plugins may not yet have been upgraded to handle the key= parameter, in which case you will need to use one of the other mechanisms.


Async models
Some plugins provide async versions of their supported models, suitable for use with Python asyncio.

To use an async model, use the llm.get_async_model() function instead of llm.get_model():

import llm
model = llm.get_async_model("gpt-4o")
You can then run a prompt using await model.prompt(...):

print(await model.prompt(
    "Five surprising names for a pet pelican"
).text())
Or use async for chunk in ... to stream the response as it is generated:

async for chunk in model.prompt(
    "Five surprising names for a pet pelican"
):
    print(chunk, end="", flush=True)
class llm.AsyncResponse(prompt: Prompt, model: _BaseModel, stream: bool, conversation: _BaseConversation | None = None, key: str | None = None, before_call: Callable[[Tool | None, ToolCall], None] | Callable[[Tool | None, ToolCall], None | Awaitable[None]] | None = None, after_call: Callable[[Tool, ToolCall, ToolResult], None] | Callable[[Tool, ToolCall, ToolResult], None | Awaitable[None]] | None = None)
Async response from a model.

async json() → dict[str, Any] | None
Return the raw JSON response from the model, if available.

async on_done(callback)
Register a callback to be called when the response is complete.

async text() → str
Return the full text of the response, executing the prompt if needed.

async tool_calls() → list[ToolCall]
Return the list of tool calls made during this response.

async usage() → Usage
Return token usage information for this response.

This await model.prompt() method takes the same arguments as the synchronous model.prompt() method, for options and attachments and key= and suchlike.

Tool functions can be sync or async
Tool functions can be both synchronous or asynchronous. The latter are defined using async def tool_name(...). Either kind of function can be passed to the tools=[...] parameter.

If an async def function is used in a synchronous context LLM will automatically execute it in a thread pool using asyncio.run(). This means the following will work even in non-asynchronous Python scripts:

async def hello(name: str) -> str:
    "Say hello to name"
    return "Hello there " + name

model = llm.get_model("gpt-4.1-mini")
chain_response = model.chain(
    "Say hello to Percival", tools=[hello]
)
print(chain_response.text())
This also works for async def methods of llm.Toolbox subclasses.

