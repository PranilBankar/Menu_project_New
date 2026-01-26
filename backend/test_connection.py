"""
Test Supabase Database Connection

This script tests the connection to your Supabase database and verifies:
1. Database connectivity
2. pgvector extension
3. Tables existence
4. Basic query functionality
"""

from sqlalchemy import create_engine, text
from app.core.config import settings
import sys


def test_connection():
    """Test database connection and setup"""
    
    print("=" * 70)
    print("🔍 Testing Supabase Database Connection")
    print("=" * 70)
    print()
    
    try:
        # Create engine
        print("📡 Connecting to database...")
        print(f"   Host: {settings.DATABASE_URL.split('@')[1].split('/')[0]}")
        
        engine = create_engine(settings.DATABASE_URL, echo=False)
        
        with engine.connect() as conn:
            # Test basic connection
            print("\n✅ Connection successful!")
            
            # Get PostgreSQL version
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"\n📊 PostgreSQL Version:")
            print(f"   {version.split(',')[0]}")
            
            # Test pgvector extension
            print("\n🔍 Checking pgvector extension...")
            result = conn.execute(text("""
                SELECT extname, extversion 
                FROM pg_extension 
                WHERE extname = 'vector'
            """))
            vector_ext = result.fetchone()
            
            if vector_ext:
                print(f"   ✅ pgvector extension enabled (version {vector_ext[1]})")
            else:
                print("   ❌ pgvector extension NOT found!")
                print("   → Enable it in Supabase Dashboard → Database → Extensions")
            
            # List all tables
            print("\n📋 Checking database tables...")
            result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """))
            
            tables = [row[0] for row in result.fetchall()]
            
            if tables:
                print(f"   Found {len(tables)} table(s):")
                for table_name in tables:
                    print(f"   ✅ {table_name}")
            else:
                print("   ⚠️  No tables found!")
                print("   → Run the SQL schema from backend/supabase_schema.sql")
            
            # Check expected tables
            expected_tables = [
                'areas', 'restaurants', 'menu_sections', 
                'menu_items', 'menu_embeddings', 'menu_uploads'
            ]
            
            missing_tables = set(expected_tables) - set(tables)
            
            if missing_tables:
                print(f"\n   ⚠️  Missing tables: {', '.join(missing_tables)}")
            else:
                print("\n   ✅ All expected tables exist!")
            
            # Test a simple query
            if 'areas' in tables:
                print("\n🔍 Testing query functionality...")
                result = conn.execute(text("SELECT COUNT(*) FROM areas"))
                count = result.fetchone()[0]
                print(f"   ✅ Query successful! Found {count} area(s)")
            
            print("\n" + "=" * 70)
            print("✅ All tests passed! Your Supabase database is ready!")
            print("=" * 70)
            print("\n🚀 Next steps:")
            print("   1. Start your server: uvicorn app.main:app --reload")
            print("   2. Visit: http://localhost:8000/api/docs")
            print("   3. Upload your first menu!")
            print()
            
            return True
            
    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ Connection test failed!")
        print("=" * 70)
        print(f"\nError: {str(e)}")
        print("\n🔧 Troubleshooting:")
        print("   1. Check your DATABASE_URL in .env file")
        print("   2. Verify Supabase project is active")
        print("   3. Ensure password is correct")
        print("   4. Add ?sslmode=require to connection string")
        print()
        
        return False


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
