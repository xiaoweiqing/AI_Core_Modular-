# migrate_constitution.py
import asyncio
import aiosqlite
import uuid
from qdrant_client import QdrantClient, models

# Import the necessary parts of your modular program
from config import settings
from core import ai_services, state
from utils.helpers import Colors, get_local_time_str

async def main_migration():
    """
    A one-time script to read all principles from the SQLite database
    and populate the corresponding vector database.
    """
    print(f"{Colors.BLUE}{'=' * 70}{Colors.ENDC}")
    print(f"{Colors.BOLD}>> Personal Constitution Vector Migration Tool <<{Colors.ENDC}")
    print(f"{Colors.BLUE}{'=' * 70}{Colors.ENDC}")

    # 1. Setup the necessary services (embedding model and Qdrant client)
    print("\n>> Step 1: Initializing services...")
    if not await ai_services.setup_embedding_model():
        print(f"❌ {Colors.RED}Failed to load the embedding model. Aborting.{Colors.ENDC}")
        return
    
    try:
        state.QDRANT_CLIENT = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
        print(f"✅ {Colors.GREEN}Services are ready.{Colors.ENDC}")
    except Exception as e:
        print(f"❌ {Colors.RED}Failed to connect to Qdrant. Is it running? Error: {e}{Colors.ENDC}")
        return

    # 2. Read all principles from the reliable SQLite database
    print("\n>> Step 2: Reading all principles from the master SQLite database...")
    try:
        async with aiosqlite.connect(str(settings.CONSTITUTION_DB)) as conn:
            cursor = await conn.execute(
                f"SELECT principle_text FROM {settings.CONSTITUTION_TABLE_NAME}"
            )
            records = await cursor.fetchall()
        
        if not records:
            print(f"{Colors.YELLOW}Warning: The SQLite constitution database is empty. Nothing to migrate.{Colors.ENDC}")
            return
        
        principles_text = [record[0] for record in records]
        print(f"✅ {Colors.GREEN}Found {len(principles_text)} principles to migrate.{Colors.ENDC}")

    except Exception as e:
        print(f"❌ {Colors.RED}Failed to read from SQLite database: {e}{Colors.ENDC}")
        return

    # 3. Generate vectors and upsert them to the Qdrant vector database
    print(f"\n>> Step 3: Generating '{settings.CURRENT_MODEL_NAME}' vectors and saving to Qdrant...")
    print(f"   Target Vector Collection: {Colors.CYAN}{settings.QDRANT_CONSTITUTION_COLLECTION}{Colors.ENDC}")
    
    points_to_upsert = []
    for i, text in enumerate(principles_text):
        print(f"   -> Processing principle {i+1}/{len(principles_text)}...", end='\r')
        
        vector = await ai_services.generate_text_vector(text)
        if vector:
            # Use the same deterministic ID logic as the main app for deduplication
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, text))
            payload = {"timestamp": get_local_time_str(), "text_chunk": text}
            
            points_to_upsert.append(
                models.PointStruct(id=point_id, vector=vector, payload=payload)
            )

    print("\n   Vector generation complete.")

    if not points_to_upsert:
        print(f"❌ {Colors.RED}Failed to generate any vectors. Aborting save.{Colors.ENDC}")
        return

    try:
        await asyncio.to_thread(
            state.QDRANT_CLIENT.upsert,
            collection_name=settings.QDRANT_CONSTITUTION_COLLECTION,
            points=points_to_upsert,
            wait=True,
        )
        print(f"✅ {Colors.GREEN}Successfully saved {len(points_to_upsert)} principles to the vector database!{Colors.ENDC}")
    except Exception as e:
        print(f"❌ {Colors.RED}An error occurred while saving to Qdrant: {e}{Colors.ENDC}")
        return

    print(f"\n{Colors.BOLD}Migration complete! Your databases are now synchronized.{Colors.ENDC}")
    print("You can now restart your main application and the Alt+Z feature should work correctly.")

if __name__ == "__main__":
    # Ensure you are running with the correct model settings
    if settings.CURRENT_MODEL_NAME != "gemma":
        print(f"{Colors.YELLOW}Warning: Your config is set to '{settings.CURRENT_MODEL_NAME}'. This script should be run with 'gemma' active.{Colors.ENDC}")
    asyncio.run(main_migration())
