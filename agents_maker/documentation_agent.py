from agno.agent import Agent
from agno.memory.v2.db.sqlite import SqliteMemoryDb
from agno.memory.v2.memory import Memory
from agno.embedder.openrouter import OpenRouterEmbedder
from agno.models.openrouter import OpenRouterModel
from agno.storage.sqlite import SqliteStorage
from agno.vectordb.lancedb import LanceDb, SearchType
from agno.knowledge.url import UrlKnowledge
from agno.tools.reasoning import ReasoningTools
from agno.tools.file import FileTools
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Set up memory with OpenRouter model
memory = Memory(
    # Use OpenRouter for creating and managing memories
    model=OpenRouterModel(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        model_id="anthropic/claude-3-5-sonnet"
    ),
    # Store memories in a SQLite database
    db=SqliteMemoryDb(
        table_name="documentation_memories", 
        db_file="tmp/documentation_agent.db"
    ),
    # Enable memory management
    delete_memories=True,
    clear_memories=True,
)

# Set up knowledge base with documentation URLs
knowledge = UrlKnowledge(
    urls=[
        # Add documentation URLs here
        "https://docs.example.com/api",
        "https://docs.example.com/guide"
    ],
    vector_db=LanceDb(
        uri="tmp/lancedb",
        table_name="documentation_store",
        search_type=SearchType.hybrid,
        # Use OpenRouter for embeddings
        embedder=OpenRouterEmbedder(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model_id="openai/text-embedding-3-small",
            dimensions=1536
        ),
    ),
)

# Store agent sessions in a SQLite database
storage = SqliteStorage(
    table_name="documentation_sessions", 
    db_file="tmp/documentation_agent.db"
)

# Create the documentation agent
documentation_agent = Agent(
    name="Documentation Assistant",
    model=OpenRouterModel(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        model_id="anthropic/claude-3-5-sonnet"
    ),
    tools=[
        ReasoningTools(add_instructions=True),
        FileTools(read_file=True, list_files=True),
    ],
    instructions=[
        "You are a documentation assistant that helps users find and understand documentation.",
        "Search your knowledge base before answering questions.",
        "Use tables to display structured data when appropriate.",
        "Include sources in your responses.",
        "When code examples are provided, explain them clearly."
    ],
    knowledge=knowledge,
    storage=storage,
    memory=memory,
    # Enable agentic memory for better context understanding
    enable_agentic_memory=True,
    # Add the chat history to the messages
    add_history_to_messages=True,
    # Number of history runs to include
    num_history_runs=5,
    user_id="documentation_user",
    markdown=True,
)

if __name__ == "__main__":
    # Load the knowledge base (first time only)
    # Comment out after first run or set recreate to False
    documentation_agent.knowledge.load(recreate=True)
    
    # Example usage
    documentation_agent.print_response(
        "How do I get started with the API?",
        stream=True,
        show_full_reasoning=True,
        stream_intermediate_steps=True,
    )
