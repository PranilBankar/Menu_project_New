-- ============================================================================
-- MENU INTELLIGENCE SYSTEM - SUPABASE DATABASE SCHEMA
-- ============================================================================
-- 
-- This SQL script creates all necessary tables, indexes, and functions
-- for the Menu Intelligence System on Supabase.
-- 
-- How to use:
-- 1. Go to your Supabase project dashboard
-- 2. Navigate to SQL Editor
-- 3. Create a new query
-- 4. Copy and paste this entire file
-- 5. Click "Run" to execute
-- 
-- ============================================================================

-- Enable required extensions
-- ============================================================================

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Vector similarity search (for embeddings)
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- CREATE TABLES
-- ============================================================================

-- Areas table: Geographic areas where restaurants are located
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS areas (
    area_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    area_name VARCHAR(255) NOT NULL,
    pincode VARCHAR(10),
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE areas IS 'Geographic areas (neighborhoods, localities) where restaurants are located';
COMMENT ON COLUMN areas.area_id IS 'Unique identifier for the area';
COMMENT ON COLUMN areas.area_name IS 'Name of the area (e.g., Koramangala, Indiranagar)';

-- Restaurants table: Restaurant information
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS restaurants (
    restaurant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    area_id UUID REFERENCES areas(area_id) ON DELETE CASCADE NOT NULL,
    restaurant_name VARCHAR(255) NOT NULL,
    cuisine_type VARCHAR(100)[],
    price_category VARCHAR(20) CHECK (price_category IN ('budget', 'mid-range', 'premium')),
    address TEXT,
    phone VARCHAR(20),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_restaurant_per_area UNIQUE(restaurant_name, area_id)
);

COMMENT ON TABLE restaurants IS 'Restaurant information and metadata';
COMMENT ON COLUMN restaurants.cuisine_type IS 'Array of cuisine types (e.g., [''Indian'', ''Chinese''])';
COMMENT ON COLUMN restaurants.price_category IS 'Price range: budget, mid-range, or premium';

-- Menu sections table: Sections within a restaurant menu
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS menu_sections (
    section_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID REFERENCES restaurants(restaurant_id) ON DELETE CASCADE NOT NULL,
    section_name VARCHAR(255) NOT NULL,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE menu_sections IS 'Menu sections (e.g., Starters, Main Course, Desserts)';
COMMENT ON COLUMN menu_sections.display_order IS 'Order in which sections should be displayed';

-- Menu items table: Individual menu items with pricing and health info
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS menu_items (
    item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    section_id UUID REFERENCES menu_sections(section_id) ON DELETE CASCADE NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    is_veg BOOLEAN DEFAULT true,
    is_available BOOLEAN DEFAULT true,
    calories INTEGER,
    health_score INTEGER CHECK (health_score BETWEEN 0 AND 100),
    health_label VARCHAR(20) CHECK (health_label IN ('healthy', 'moderate', 'unhealthy')),
    spice_level VARCHAR(20) CHECK (spice_level IN ('mild', 'medium', 'hot', 'extra-hot')),
    allergens VARCHAR(100)[],
    tags VARCHAR(50)[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE menu_items IS 'Individual menu items with nutritional and health information';
COMMENT ON COLUMN menu_items.health_score IS 'Health score from 0 (unhealthy) to 100 (very healthy)';
COMMENT ON COLUMN menu_items.health_label IS 'Categorical health label based on score';
COMMENT ON COLUMN menu_items.allergens IS 'Array of allergens (e.g., [''nuts'', ''dairy''])';
COMMENT ON COLUMN menu_items.tags IS 'Array of tags (e.g., [''grilled'', ''spicy'', ''vegan''])';

-- Menu embeddings table: Vector embeddings for semantic search
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS menu_embeddings (
    embedding_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    item_id UUID REFERENCES menu_items(item_id) ON DELETE CASCADE NOT NULL UNIQUE,
    embedding vector(384),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE menu_embeddings IS 'Vector embeddings for semantic search of menu items';
COMMENT ON COLUMN menu_embeddings.embedding IS 'Vector embedding (384 dimensions for MiniLM model)';
COMMENT ON COLUMN menu_embeddings.metadata IS 'Additional metadata stored as JSON';

-- Menu uploads table: Track menu image uploads and OCR processing
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS menu_uploads (
    upload_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID REFERENCES restaurants(restaurant_id) ON DELETE SET NULL,
    image_path VARCHAR(500) NOT NULL,
    ocr_status VARCHAR(20) DEFAULT 'pending' CHECK (ocr_status IN ('pending', 'processing', 'completed', 'failed')),
    ocr_result JSONB,
    structured_data JSONB,
    error_message TEXT,
    uploaded_by VARCHAR(100),
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE
);

COMMENT ON TABLE menu_uploads IS 'Track menu image uploads and OCR processing status';
COMMENT ON COLUMN menu_uploads.ocr_status IS 'Status: pending, processing, completed, or failed';
COMMENT ON COLUMN menu_uploads.ocr_result IS 'Raw OCR output stored as JSON';
COMMENT ON COLUMN menu_uploads.structured_data IS 'LLM-structured menu data as JSON';

-- ============================================================================
-- CREATE INDEXES FOR PERFORMANCE
-- ============================================================================

-- Relationship indexes
CREATE INDEX IF NOT EXISTS idx_restaurants_area ON restaurants(area_id);
CREATE INDEX IF NOT EXISTS idx_menu_sections_restaurant ON menu_sections(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_menu_items_section ON menu_items(section_id);
CREATE INDEX IF NOT EXISTS idx_menu_embeddings_item ON menu_embeddings(item_id);

-- Search and filter indexes
CREATE INDEX IF NOT EXISTS idx_menu_items_price ON menu_items(price);
CREATE INDEX IF NOT EXISTS idx_menu_items_health ON menu_items(health_label);
CREATE INDEX IF NOT EXISTS idx_menu_items_name ON menu_items(item_name);
CREATE INDEX IF NOT EXISTS idx_menu_items_veg ON menu_items(is_veg);
CREATE INDEX IF NOT EXISTS idx_areas_city ON areas(city);
CREATE INDEX IF NOT EXISTS idx_areas_name ON areas(area_name);
CREATE INDEX IF NOT EXISTS idx_restaurants_active ON restaurants(is_active);

-- Vector similarity index (IVFFlat for fast approximate nearest neighbor search)
-- Note: This index is created after you have some data
CREATE INDEX IF NOT EXISTS idx_menu_embeddings_vector 
ON menu_embeddings USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- ============================================================================
-- CREATE FUNCTIONS AND TRIGGERS
-- ============================================================================

-- Function to automatically update updated_at timestamp
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for automatic updated_at updates
-- ----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS update_areas_updated_at ON areas;
CREATE TRIGGER update_areas_updated_at 
    BEFORE UPDATE ON areas
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_restaurants_updated_at ON restaurants;
CREATE TRIGGER update_restaurants_updated_at 
    BEFORE UPDATE ON restaurants
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_menu_items_updated_at ON menu_items;
CREATE TRIGGER update_menu_items_updated_at 
    BEFORE UPDATE ON menu_items
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- HELPER VIEWS (Optional - for easier querying)
-- ============================================================================

-- View: Full menu with all details
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_full_menu AS
SELECT 
    mi.item_id,
    mi.item_name,
    mi.description,
    mi.price,
    mi.is_veg,
    mi.health_score,
    mi.health_label,
    mi.tags,
    ms.section_name,
    r.restaurant_name,
    r.cuisine_type,
    r.price_category,
    a.area_name,
    a.city,
    a.state
FROM menu_items mi
JOIN menu_sections ms ON mi.section_id = ms.section_id
JOIN restaurants r ON ms.restaurant_id = r.restaurant_id
JOIN areas a ON r.area_id = a.area_id
WHERE mi.is_available = true AND r.is_active = true;

COMMENT ON VIEW v_full_menu IS 'Complete menu view with all related information';

-- View: Restaurant statistics
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_restaurant_stats AS
SELECT 
    r.restaurant_id,
    r.restaurant_name,
    a.area_name,
    a.city,
    COUNT(DISTINCT ms.section_id) as section_count,
    COUNT(DISTINCT mi.item_id) as item_count,
    AVG(mi.price) as avg_price,
    AVG(mi.health_score) as avg_health_score,
    COUNT(DISTINCT mi.item_id) FILTER (WHERE mi.is_veg = true) as veg_items,
    COUNT(DISTINCT mi.item_id) FILTER (WHERE mi.is_veg = false) as non_veg_items
FROM restaurants r
JOIN areas a ON r.area_id = a.area_id
LEFT JOIN menu_sections ms ON r.restaurant_id = ms.restaurant_id
LEFT JOIN menu_items mi ON ms.section_id = mi.section_id
WHERE r.is_active = true
GROUP BY r.restaurant_id, r.restaurant_name, a.area_name, a.city;

COMMENT ON VIEW v_restaurant_stats IS 'Statistical summary for each restaurant';

-- ============================================================================
-- SAMPLE DATA (Optional - for testing)
-- ============================================================================

-- Insert sample area
INSERT INTO areas (area_name, city, pincode, state)
VALUES ('Koramangala', 'Bangalore', '560034', 'Karnataka')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) - Optional but Recommended
-- ============================================================================

-- Enable RLS on all tables
ALTER TABLE areas ENABLE ROW LEVEL SECURITY;
ALTER TABLE restaurants ENABLE ROW LEVEL SECURITY;
ALTER TABLE menu_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE menu_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE menu_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE menu_uploads ENABLE ROW LEVEL SECURITY;

-- Create policies (allow all for now - customize based on your auth needs)
CREATE POLICY "Allow all access to areas" ON areas FOR ALL USING (true);
CREATE POLICY "Allow all access to restaurants" ON restaurants FOR ALL USING (true);
CREATE POLICY "Allow all access to menu_sections" ON menu_sections FOR ALL USING (true);
CREATE POLICY "Allow all access to menu_items" ON menu_items FOR ALL USING (true);
CREATE POLICY "Allow all access to menu_embeddings" ON menu_embeddings FOR ALL USING (true);
CREATE POLICY "Allow all access to menu_uploads" ON menu_uploads FOR ALL USING (true);

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check all tables were created
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- Check extensions
SELECT extname, extversion 
FROM pg_extension 
WHERE extname IN ('uuid-ossp', 'vector');

-- Check indexes
SELECT 
    schemaname,
    tablename,
    indexname
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

-- ============================================================================
-- SETUP COMPLETE!
-- ============================================================================
-- 
-- ✅ All tables created
-- ✅ Indexes created for performance
-- ✅ Triggers set up for automatic timestamps
-- ✅ Views created for easier querying
-- ✅ Row Level Security enabled
-- 
-- Next steps:
-- 1. Update your .env file with Supabase connection string
-- 2. Run: python backend/test_connection.py
-- 3. Start your server: uvicorn app.main:app --reload
-- 4. Upload your first menu!
-- 
-- ============================================================================
