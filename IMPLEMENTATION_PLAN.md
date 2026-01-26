# 🎯 Menu Intelligence System - Detailed Implementation Plan

## Executive Summary

This document provides a step-by-step implementation guide for building a production-ready Menu OCR → Database → Chatbot system.

---

## Phase 1: Foundation & Core Infrastructure (Week 1-2)

### 1.1 Environment Setup

**Tasks:**
- [ ] Initialize Python virtual environment
- [ ] Install PostgreSQL 14+ with pgvector extension
- [ ] Setup Redis server
- [ ] Create project directory structure
- [ ] Initialize Git repository

**Commands:**
```bash
# Python environment
python -m venv venv
source venv/bin/activate

# Install core dependencies
pip install fastapi uvicorn sqlalchemy psycopg2-binary alembic pydantic python-dotenv

# Install OCR dependencies
pip install paddleocr opencv-python pillow

# Install NLP dependencies
pip install sentence-transformers transformers torch
```

**Deliverables:**
- Working development environment
- Database connection established
- Basic project structure

---

### 1.2 Database Schema Design & Implementation

**Database Schema:**

```sql
-- Areas table
CREATE TABLE areas (
    area_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    area_name VARCHAR(255) NOT NULL,
    pincode VARCHAR(10),
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Restaurants table
CREATE TABLE restaurants (
    restaurant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    area_id UUID REFERENCES areas(area_id) ON DELETE CASCADE,
    restaurant_name VARCHAR(255) NOT NULL,
    cuisine_type VARCHAR(100)[],  -- Array of cuisines
    price_category VARCHAR(20) CHECK (price_category IN ('budget', 'mid-range', 'premium')),
    address TEXT,
    phone VARCHAR(20),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(restaurant_name, area_id)
);

-- Menu sections table
CREATE TABLE menu_sections (
    section_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(restaurant_id) ON DELETE CASCADE,
    section_name VARCHAR(255) NOT NULL,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Menu items table
CREATE TABLE menu_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id UUID REFERENCES menu_sections(section_id) ON DELETE CASCADE,
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Menu embeddings table
CREATE TABLE menu_embeddings (
    embedding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id UUID REFERENCES menu_items(item_id) ON DELETE CASCADE,
    embedding vector(384),  -- MiniLM embedding dimension
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(item_id)
);

-- Menu upload history
CREATE TABLE menu_uploads (
    upload_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(restaurant_id),
    image_path VARCHAR(500) NOT NULL,
    ocr_status VARCHAR(20) DEFAULT 'pending',
    ocr_result JSONB,
    error_message TEXT,
    uploaded_by VARCHAR(100),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_restaurants_area ON restaurants(area_id);
CREATE INDEX idx_menu_sections_restaurant ON menu_sections(restaurant_id);
CREATE INDEX idx_menu_items_section ON menu_items(section_id);
CREATE INDEX idx_menu_items_price ON menu_items(price);
CREATE INDEX idx_menu_items_health ON menu_items(health_label);
CREATE INDEX idx_menu_embeddings_item ON menu_embeddings(item_id);

-- Vector similarity index
CREATE INDEX ON menu_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**SQLAlchemy Models:**

Location: `backend/app/models/`

Files to create:
- `area.py` - Area model
- `restaurant.py` - Restaurant model
- `menu.py` - Menu sections and items
- `embedding.py` - Embeddings model
- `upload.py` - Upload history

**Tasks:**
- [ ] Create Alembic migration scripts
- [ ] Implement SQLAlchemy models
- [ ] Create Pydantic schemas for validation
- [ ] Write database utility functions
- [ ] Test CRUD operations

---

### 1.3 Basic OCR Pipeline

**OCR Service Architecture:**

```python
# backend/app/services/ocr/ocr_engine.py

class OCREngine:
    """
    Handles OCR extraction from menu images
    """
    
    def __init__(self):
        self.paddle_ocr = PaddleOCR(use_angle_cls=True, lang='en')
    
    def preprocess_image(self, image_path: str) -> np.ndarray:
        """
        Preprocessing steps:
        1. Read image
        2. Convert to grayscale
        3. Enhance contrast
        4. Deskew
        5. Denoise
        """
        pass
    
    def extract_text(self, image_path: str) -> List[Dict]:
        """
        Extract text with bounding boxes
        Returns: [{"text": "...", "bbox": [...], "confidence": 0.95}]
        """
        pass
    
    def clean_text(self, ocr_results: List[Dict]) -> List[Dict]:
        """
        Clean OCR output:
        - Remove noise
        - Normalize currency symbols
        - Fix common OCR errors
        """
        pass
```

**Tasks:**
- [ ] Implement image preprocessing pipeline
- [ ] Integrate PaddleOCR
- [ ] Create text cleaning utilities
- [ ] Handle multiple image formats
- [ ] Add error handling and logging
- [ ] Test with sample menu images

---

### 1.4 FastAPI Backend Setup

**API Structure:**

```
backend/app/
├── main.py                 # FastAPI app initialization
├── api/
│   ├── v1/
│   │   ├── endpoints/
│   │   │   ├── menus.py    # Menu upload & management
│   │   │   ├── areas.py    # Area management
│   │   │   ├── restaurants.py
│   │   │   └── chatbot.py  # Chatbot queries
│   │   └── api.py          # API router
├── core/
│   ├── config.py           # Settings & environment
│   ├── security.py         # Authentication
│   └── database.py         # DB connection
├── models/                 # SQLAlchemy models
├── schemas/                # Pydantic schemas
└── services/               # Business logic
```

**Key Endpoints (Phase 1):**

```python
# Menu Upload
POST /api/v1/menus/upload
- Upload menu image
- Trigger OCR processing
- Return upload_id

GET /api/v1/menus/uploads/{upload_id}/status
- Check OCR processing status

# Area Management
POST /api/v1/areas
GET /api/v1/areas
GET /api/v1/areas/{area_id}/restaurants

# Restaurant Management
POST /api/v1/restaurants
GET /api/v1/restaurants/{restaurant_id}
PUT /api/v1/restaurants/{restaurant_id}
```

**Tasks:**
- [ ] Setup FastAPI application
- [ ] Implement CORS middleware
- [ ] Create database session management
- [ ] Build menu upload endpoint
- [ ] Add file upload handling
- [ ] Implement basic authentication
- [ ] Write API documentation (OpenAPI)

---

### 1.5 Admin Upload Panel (Basic)

**Frontend Stack:**
- React 18+
- Vite
- TailwindCSS
- React Query (data fetching)
- React Dropzone (file upload)

**Components:**
```
frontend/admin/src/
├── components/
│   ├── MenuUpload.jsx      # Drag-and-drop upload
│   ├── AreaSelector.jsx    # Select area
│   ├── RestaurantForm.jsx  # Restaurant details
│   └── OCRPreview.jsx      # Show OCR results
├── pages/
│   ├── Dashboard.jsx
│   ├── UploadMenu.jsx
│   └── MenuList.jsx
└── services/
    └── api.js              # API client
```

**Tasks:**
- [ ] Initialize React project with Vite
- [ ] Setup TailwindCSS
- [ ] Create upload interface
- [ ] Implement area/restaurant selection
- [ ] Show OCR processing status
- [ ] Display extracted text for review
- [ ] Add manual correction interface

---

## Phase 2: Intelligence Layer (Week 3-4)

### 2.1 LLM-Assisted Menu Structuring

**Approach:**

Use GPT-4 or Llama to convert raw OCR text into structured JSON.

**Prompt Template:**

```python
MENU_STRUCTURING_PROMPT = """
You are a menu data extraction expert. Convert the following OCR text from a restaurant menu into structured JSON.

OCR Text:
{ocr_text}

Extract:
1. Restaurant name (if present)
2. Menu sections (e.g., "Starters", "Main Course", "Beverages")
3. Items under each section with:
   - Item name
   - Description (if any)
   - Price (in INR)
   - Vegetarian/Non-vegetarian indicator
   - Any health-related keywords (grilled, fried, sugar-free, etc.)

Output Format:
{{
  "restaurant_name": "...",
  "sections": [
    {{
      "section_name": "...",
      "items": [
        {{
          "name": "...",
          "description": "...",
          "price": 180,
          "is_veg": true,
          "keywords": ["grilled", "healthy"]
        }}
      ]
    }}
  ]
}}

Rules:
- If price is not found, set to null
- Detect veg/non-veg from symbols (🟢, 🔴) or keywords
- Normalize prices (remove ₹, Rs, etc.)
- Group items logically into sections
"""
```

**Implementation:**

```python
# backend/app/services/nlp/menu_structurer.py

class MenuStructurer:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def structure_menu(self, ocr_text: str) -> Dict:
        """
        Convert OCR text to structured menu data
        """
        prompt = MENU_STRUCTURING_PROMPT.format(ocr_text=ocr_text)
        response = await self.llm.generate(prompt)
        return json.loads(response)
    
    def validate_structure(self, menu_data: Dict) -> bool:
        """
        Validate extracted menu structure
        """
        pass
```

**Tasks:**
- [ ] Integrate OpenAI/Llama API
- [ ] Create prompt templates
- [ ] Implement menu structuring service
- [ ] Add validation logic
- [ ] Handle edge cases (missing prices, unclear sections)
- [ ] Test with diverse menu formats

---

### 2.2 Health Scoring System

**Rule-Based Scoring:**

```python
# backend/app/services/health/health_scorer.py

class HealthScorer:
    HEALTH_RULES = {
        # Positive indicators
        'grilled': +10,
        'steamed': +10,
        'baked': +8,
        'roasted': +8,
        'salad': +15,
        'vegetarian': +5,
        'low-fat': +10,
        'sugar-free': +10,
        'whole-grain': +10,
        
        # Negative indicators
        'fried': -15,
        'deep-fried': -20,
        'butter': -8,
        'cream': -10,
        'cheese': -5,
        'sugar': -8,
        'processed': -10,
    }
    
    def calculate_score(self, item_name: str, description: str) -> int:
        """
        Calculate health score (0-100)
        """
        score = 50  # Base score
        text = f"{item_name} {description}".lower()
        
        for keyword, points in self.HEALTH_RULES.items():
            if keyword in text:
                score += points
        
        # Clamp between 0-100
        return max(0, min(100, score))
    
    def get_health_label(self, score: int) -> str:
        """
        Convert score to label
        """
        if score >= 70:
            return 'healthy'
        elif score >= 40:
            return 'moderate'
        else:
            return 'unhealthy'
```

**ML-Based Classification (Optional):**

Train a DistilBERT classifier on food health dataset.

**Tasks:**
- [ ] Implement rule-based scorer
- [ ] Create health keyword dictionary
- [ ] Add calorie estimation (optional)
- [ ] Test scoring accuracy
- [ ] (Optional) Train ML classifier
- [ ] Integrate into menu processing pipeline

---

### 2.3 Embedding Generation

**Embedding Strategy:**

Generate embeddings for semantic search.

```python
# backend/app/services/nlp/embedding_service.py

from sentence_transformers import SentenceTransformer

class EmbeddingService:
    def __init__(self):
        self.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    
    def generate_item_embedding(self, item: Dict) -> np.ndarray:
        """
        Create embedding from item data
        """
        # Combine relevant fields
        text = f"{item['name']} {item['description']} {item['section_name']} {item['restaurant_name']}"
        
        # Generate embedding
        embedding = self.model.encode(text)
        return embedding
    
    async def batch_generate(self, items: List[Dict]) -> List[np.ndarray]:
        """
        Generate embeddings in batch for efficiency
        """
        texts = [
            f"{item['name']} {item['description']}"
            for item in items
        ]
        embeddings = self.model.encode(texts, batch_size=32)
        return embeddings
```

**Tasks:**
- [ ] Setup Sentence Transformers
- [ ] Implement embedding generation
- [ ] Create batch processing
- [ ] Store embeddings in pgvector
- [ ] Build vector similarity search
- [ ] Test search relevance

---

### 2.4 Duplicate Detection

**Approach:**

Use embeddings to detect duplicate menu items across uploads.

```python
def find_duplicates(new_item_embedding, existing_embeddings, threshold=0.95):
    """
    Find similar items using cosine similarity
    """
    similarities = cosine_similarity([new_item_embedding], existing_embeddings)
    duplicates = np.where(similarities > threshold)[1]
    return duplicates
```

**Tasks:**
- [ ] Implement similarity-based duplicate detection
- [ ] Add manual review interface
- [ ] Create merge/update logic
- [ ] Test with real menu data

---

## Phase 3: Chatbot Intelligence (Week 5-6)

### 3.1 Query Parsing & Intent Extraction

**Query Examples:**
- "Healthy lunch under ₹200 near me"
- "Veg starters in Koramangala"
- "Low-calorie desserts"

**Parser Implementation:**

```python
# backend/app/services/chatbot/query_parser.py

class QueryParser:
    def parse_query(self, query: str, user_location: str) -> Dict:
        """
        Extract filters from natural language query
        """
        filters = {
            'price_max': None,
            'price_min': None,
            'health_label': None,
            'is_veg': None,
            'meal_type': None,
            'cuisine': None,
            'area': user_location,
            'keywords': []
        }
        
        # Price extraction
        price_match = re.search(r'under ₹?(\d+)', query.lower())
        if price_match:
            filters['price_max'] = int(price_match.group(1))
        
        # Health keywords
        if any(word in query.lower() for word in ['healthy', 'low-calorie', 'light']):
            filters['health_label'] = 'healthy'
        
        # Veg/Non-veg
        if 'veg' in query.lower() and 'non' not in query.lower():
            filters['is_veg'] = True
        
        # Meal type
        for meal in ['breakfast', 'lunch', 'dinner', 'snack']:
            if meal in query.lower():
                filters['meal_type'] = meal
        
        return filters
```

**Tasks:**
- [ ] Implement regex-based filter extraction
- [ ] Add LLM-based intent classification (optional)
- [ ] Handle complex queries
- [ ] Test with diverse query patterns

---

### 3.2 Hybrid Search (SQL + Vector)

**Search Strategy:**

1. **SQL Filtering**: Apply hard constraints (price, veg, area)
2. **Vector Search**: Rank by semantic similarity
3. **Combine**: Merge results with weighted scoring

```python
# backend/app/services/chatbot/search_engine.py

class HybridSearchEngine:
    async def search(self, query: str, filters: Dict) -> List[Dict]:
        """
        Hybrid SQL + Vector search
        """
        # Generate query embedding
        query_embedding = self.embedding_service.encode(query)
        
        # Build SQL query with filters
        sql_query = """
        SELECT 
            mi.item_id,
            mi.item_name,
            mi.description,
            mi.price,
            mi.health_score,
            r.restaurant_name,
            a.area_name,
            me.embedding,
            (me.embedding <=> %s::vector) as similarity
        FROM menu_items mi
        JOIN menu_sections ms ON mi.section_id = ms.section_id
        JOIN restaurants r ON ms.restaurant_id = r.restaurant_id
        JOIN areas a ON r.area_id = a.area_id
        JOIN menu_embeddings me ON mi.item_id = me.item_id
        WHERE 1=1
        """
        
        params = [query_embedding.tolist()]
        
        # Apply filters
        if filters.get('price_max'):
            sql_query += " AND mi.price <= %s"
            params.append(filters['price_max'])
        
        if filters.get('is_veg') is not None:
            sql_query += " AND mi.is_veg = %s"
            params.append(filters['is_veg'])
        
        if filters.get('health_label'):
            sql_query += " AND mi.health_label = %s"
            params.append(filters['health_label'])
        
        if filters.get('area'):
            sql_query += " AND a.area_name = %s"
            params.append(filters['area'])
        
        # Order by similarity
        sql_query += " ORDER BY similarity ASC LIMIT 20"
        
        # Execute query
        results = await self.db.execute(sql_query, params)
        return results
```

**Tasks:**
- [ ] Implement hybrid search
- [ ] Optimize vector similarity queries
- [ ] Add result ranking logic
- [ ] Test search performance
- [ ] Create search analytics

---

### 3.3 RAG Implementation

**RAG Architecture:**

```python
# backend/app/services/chatbot/rag_chatbot.py

class RAGChatbot:
    def __init__(self, search_engine, llm_client):
        self.search_engine = search_engine
        self.llm = llm_client
    
    async def answer_query(self, query: str, user_context: Dict) -> str:
        """
        RAG pipeline:
        1. Parse query
        2. Search database
        3. Build context
        4. Generate response
        """
        # Parse query
        filters = self.parser.parse_query(query, user_context['area'])
        
        # Search
        results = await self.search_engine.search(query, filters)
        
        # Build context
        context = self._build_context(results)
        
        # Generate response
        prompt = f"""
        User Query: {query}
        
        Available Menu Items:
        {context}
        
        Provide a helpful, conversational response listing the best options.
        Include restaurant names, prices, and why each item matches the query.
        """
        
        response = await self.llm.generate(prompt)
        return response
    
    def _build_context(self, results: List[Dict]) -> str:
        """
        Format search results into LLM context
        """
        context_parts = []
        for item in results:
            context_parts.append(
                f"- {item['item_name']} at {item['restaurant_name']} "
                f"(₹{item['price']}, Health: {item['health_score']}/100)"
            )
        return "\n".join(context_parts)
```

**Tasks:**
- [ ] Implement RAG pipeline
- [ ] Create prompt templates
- [ ] Add conversation history
- [ ] Implement streaming responses
- [ ] Test chatbot accuracy

---

### 3.4 Frontend Chatbot UI

**Components:**

```jsx
// frontend/chatbot/src/components/ChatInterface.jsx

const ChatInterface = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  
  const sendMessage = async () => {
    const response = await fetch('/api/v1/chat/query', {
      method: 'POST',
      body: JSON.stringify({ query: input, area: userArea })
    });
    
    const data = await response.json();
    setMessages([...messages, { user: input, bot: data.response }]);
  };
  
  return (
    <div className="chat-container">
      <MessageList messages={messages} />
      <InputBox value={input} onChange={setInput} onSend={sendMessage} />
    </div>
  );
};
```

**Tasks:**
- [ ] Build chat interface
- [ ] Add message bubbles
- [ ] Implement typing indicators
- [ ] Show menu item cards
- [ ] Add location selector
- [ ] Create mobile-responsive design

---

## Phase 4: Production Optimization (Week 7-8)

### 4.1 Performance Optimization

**Caching Strategy:**

```python
# Redis caching for popular queries
@cache(ttl=3600)
async def get_popular_items(area_id: str):
    """Cache popular items per area"""
    pass

# Precompute embeddings
async def precompute_all_embeddings():
    """Run nightly job to update embeddings"""
    pass
```

**Tasks:**
- [ ] Implement Redis caching
- [ ] Add database query optimization
- [ ] Create indexes on frequently queried fields
- [ ] Implement pagination
- [ ] Add CDN for images
- [ ] Optimize embedding search with HNSW index

---

### 4.2 Analytics Dashboard

**Metrics to Track:**
- Total menus uploaded
- OCR success rate
- Popular queries
- Most searched items
- Average response time
- User engagement

**Tasks:**
- [ ] Create analytics models
- [ ] Build dashboard UI
- [ ] Add real-time metrics
- [ ] Implement query analytics
- [ ] Track user behavior

---

### 4.3 Deployment

**Infrastructure:**

```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: pgvector/pgvector:pg14
    environment:
      POSTGRES_DB: menu_db
      POSTGRES_USER: menu_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql://menu_user:${DB_PASSWORD}@postgres:5432/menu_db
      REDIS_URL: redis://redis:6379
    depends_on:
      - postgres
      - redis
  
  frontend:
    build: ./frontend/admin
    ports:
      - "3000:3000"
```

**Tasks:**
- [ ] Create Dockerfiles
- [ ] Setup docker-compose
- [ ] Configure environment variables
- [ ] Setup CI/CD pipeline
- [ ] Deploy to AWS/GCP
- [ ] Configure domain & SSL
- [ ] Setup monitoring (Sentry, DataDog)

---

## Success Metrics

### Technical Metrics
- OCR accuracy > 90%
- Query response time < 500ms
- Search relevance > 85%
- System uptime > 99.5%

### Business Metrics
- Number of menus digitized
- Active users
- Query satisfaction rate
- Restaurant partnerships

---

## Next Steps

**Immediate Actions:**
1. Setup development environment
2. Create database schema
3. Implement basic OCR pipeline
4. Build menu upload API
5. Create admin panel prototype

**Would you like me to:**
1. ✅ Start implementing Phase 1 code (database models, OCR service)?
2. ✅ Create detailed API specifications?
3. ✅ Build the frontend admin panel?
4. ✅ Setup the development environment?

Let me know which component you'd like to tackle first!
