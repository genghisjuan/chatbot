import os
from pinecone import Pinecone
from app.core.config import settings

def check_stats():
    print("-" * 50)
    print("CHECKING PINECONE INDEX STATS")
    print("-" * 50)
    
    if settings.PINECONE_API_KEY == "changeme":
        print("❌ API Key missing.")
        return

    try:
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index(settings.PINECONE_INDEX_NAME)
        
        stats = index.describe_index_stats()
        print("\nINDEX STATISTICS:")
        print(stats)
        
        count = stats.get('total_vector_count', 0)
        print(f"\n✅ TOTAL VECTORS: {count}")
        
        if count < 100:
            print("⚠️ WARNING: Vector count is suspicious! (Too low)")
        else:
            print("✅ Data volume looks healthy.")

    except Exception as e:
        print(f"❌ Error getting stats: {e}")

if __name__ == "__main__":
    check_stats()
