# 🍽️ Smart Menu Intelligence System

An end-to-end AI-powered system for menu digitization, structured storage, and intelligent food discovery through natural language queries.

## 🎯 Project Overview

This system enables:
- **Menu Ingestion**: Upload menu card images → Automatic OCR → Structured data extraction
- **Intelligent Database**: Area-based organization with restaurants, sections, and menu items
- **Smart Chatbot**: Natural language queries like "Healthy lunch under ₹200 near me"

## 🏗️ Architecture

```
Menu Image → OCR Engine → NLP Structuring → Database → Embeddings → RAG Chatbot
```

## 🛠️ Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.10+)
- **Database**: PostgreSQL with pgvector extension
- **Cache**: Redis
- **OCR**: PaddleOCR (primary), Google Vision API (backup)
- **NLP/LLM**: 
  - Sentence Transformers (embeddings)
  - OpenAI/Llama (reasoning layer)

### Frontend
- **Admin Panel**: React + TailwindCSS
- **User Chatbot**: React + WebSocket

### ML/AI
- Document AI: LayoutLMv3 (optional)
- Embeddings: sentence-transformers/all-MiniLM-L6-v2
- Health Classification: Custom DistilBERT fine-tuned model

## 📁 Project Structure

```
Menu_Project/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI endpoints
│   │   ├── core/             # Config, security, database
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # Business logic
│   │   │   ├── ocr/          # OCR pipeline
│   │   │   ├── nlp/          # Text processing & embeddings
│   │   │   ├── chatbot/      # RAG chatbot logic
│   │   │   └── health/       # Health scoring
│   │   └── utils/            # Helper functions
│   ├── alembic/              # Database migrations
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── admin/                # Admin upload panel
│   └── chatbot/              # User chatbot UI
├── ml_models/
│   ├── health_classifier/    # Health classification model
│   └── embeddings/           # Cached embedding models
├── scripts/
│   ├── setup_db.py
│   └── seed_data.py
├── data/
│   ├── raw/                  # Uploaded menu images
│   ├── processed/            # Cleaned OCR outputs
│   └── embeddings/           # Precomputed embeddings
├── docs/
│   ├── api/                  # API documentation
│   └── architecture/         # System design docs
└── docker-compose.yml
```

## 🗄️ Database Schema

### Core Tables
- `areas`: Geographic areas (area_id, area_name, pincode, city)
- `restaurants`: Restaurant info (restaurant_id, area_id, name, cuisine_type, price_category)
- `menu_sections`: Menu sections (section_id, restaurant_id, section_name)
- `menu_items`: Individual items (item_id, section_id, name, description, price, is_veg, health_score)
- `menu_embeddings`: Vector embeddings (item_id, embedding, metadata)

## 🚀 Quick Start

### Prerequisites
```bash
- Python 3.10+
- PostgreSQL 14+ with pgvector
- Redis
- Node.js 18+
```

### Installation

1. **Clone and setup backend**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Setup database**
```bash
python scripts/setup_db.py
alembic upgrade head
```

3. **Run backend**
```bash
uvicorn app.main:app --reload
```

4. **Setup frontend**
```bash
cd frontend/admin
npm install
npm run dev
```

## 📋 Development Phases

### ✅ Phase 1: Foundation (Week 1-2)
- [x] Project structure
- [ ] Database schema & migrations
- [ ] Basic OCR pipeline (PaddleOCR)
- [ ] Admin upload API
- [ ] Manual menu structuring UI

### 🔄 Phase 2: Intelligence (Week 3-4)
- [ ] Auto menu structuring (LLM-assisted)
- [ ] Health scoring system
- [ ] Embedding generation pipeline
- [ ] Duplicate detection

### 🎯 Phase 3: Chatbot (Week 5-6)
- [ ] Query parsing & intent extraction
- [ ] Hybrid SQL + Vector search
- [ ] RAG implementation
- [ ] Area-specific filtering

### 🚀 Phase 4: Production (Week 7-8)
- [ ] Performance optimization
- [ ] Caching layer (Redis)
- [ ] Analytics dashboard
- [ ] Deployment (AWS/GCP)

## 🔑 Key Features

### Menu Processing Pipeline
1. **Image Preprocessing**: Grayscale, contrast enhancement, deskew
2. **OCR Extraction**: PaddleOCR with bounding boxes
3. **Text Cleaning**: Normalize prices, remove noise
4. **Structure Detection**: LLM-assisted section & item extraction
5. **Health Scoring**: Rule-based + ML classification
6. **Embedding Generation**: Semantic vectors for search

### Chatbot Capabilities
- Natural language understanding
- Multi-filter queries (price, health, cuisine, area)
- Ranked recommendations
- Context-aware responses

## 🧪 Testing

```bash
# Backend tests
pytest tests/ -v

# Frontend tests
npm test
```

## 📊 API Endpoints

### Menu Management
- `POST /api/v1/menus/upload` - Upload menu image
- `GET /api/v1/menus/{menu_id}` - Get menu details
- `PUT /api/v1/menus/{menu_id}` - Update menu
- `DELETE /api/v1/menus/{menu_id}` - Delete menu

### Chatbot
- `POST /api/v1/chat/query` - Send natural language query
- `GET /api/v1/chat/history` - Get chat history

### Admin
- `GET /api/v1/areas` - List all areas
- `POST /api/v1/restaurants` - Add restaurant
- `GET /api/v1/analytics` - Get system analytics

## 🔒 Security

- JWT authentication
- Rate limiting
- Input validation
- SQL injection prevention
- CORS configuration

## 📈 Scaling Considerations

- Async OCR processing with Celery
- Redis caching for popular queries
- CDN for menu images
- Database indexing on frequently queried fields
- Horizontal scaling with load balancer

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

## 📝 License

MIT License - see LICENSE file for details

## 👨‍💻 Author

Pranil Bankar

## 🙏 Acknowledgments

- PaddleOCR team
- Sentence Transformers
- FastAPI community
