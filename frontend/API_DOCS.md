# Menu Intelligence System — API Documentation

**Base URL:** `https://<your-deployed-url>/api/v1`  
**Swagger UI:** `https://<your-deployed-url>/api/docs`  
**Content-Type:** `application/json` (except file uploads)

---

## 1. Health Check

```
GET /health
```

**Response** `200`
```json
{ "status": "healthy", "version": "1.0.0" }
```

---

## 2. Areas

### 2.1 Create Area

```
POST /api/v1/areas/
```

**Request Body**
```json
{
  "area_name": "VR Mall",
  "city": "Nagpur",
  "pincode": "440001",    // optional
  "state": "Maharashtra"  // optional
}
```

**Response** `200`
```json
{
  "area_id": "a1b2c3d4-...",
  "area_name": "VR Mall",
  "city": "Nagpur",
  "pincode": "440001",
  "state": "Maharashtra"
}
```

### 2.2 List Areas

```
GET /api/v1/areas/?city=Nagpur&skip=0&limit=100
```

All query params are optional. `city` does a case-insensitive partial match.

**Response** `200`
```json
[
  {
    "area_id": "a1b2c3d4-...",
    "area_name": "VR Mall",
    "city": "Nagpur",
    "pincode": "440001",
    "state": "Maharashtra"
  }
]
```

### 2.3 Get Area by ID

```
GET /api/v1/areas/{area_id}
```

**Response** `200` — same shape as above  
**Response** `404` — `{"detail": "Area not found"}`

### 2.4 Get Restaurants in Area

```
GET /api/v1/areas/{area_id}/restaurants
```

**Response** `200`
```json
{
  "area": {
    "area_id": "a1b2c3d4-...",
    "area_name": "VR Mall",
    "city": "Nagpur"
  },
  "restaurants": [
    {
      "restaurant_id": "e5f6g7h8-...",
      "restaurant_name": "Pranil Da Dhaba",
      "cuisine_type": ["North Indian", "Chinese"],
      "price_category": "mid-range"
    }
  ]
}
```

---

## 3. Restaurants

### 3.1 Create Restaurant

```
POST /api/v1/restaurants/
```

**Request Body**
```json
{
  "restaurant_name": "Pranil Da Dhaba",
  "area_id": "a1b2c3d4-...",
  "cuisine_type": ["North Indian", "Chinese"],  // optional
  "price_category": "mid-range",                // optional: budget | mid-range | premium
  "address": "Shop 12, VR Mall",                // optional
  "phone": "9876543210"                         // optional
}
```

**Response** `200`
```json
{
  "restaurant_id": "e5f6g7h8-...",
  "area_id": "a1b2c3d4-...",
  "restaurant_name": "Pranil Da Dhaba",
  "cuisine_type": ["North Indian", "Chinese"],
  "price_category": "mid-range",
  "address": "Shop 12, VR Mall",
  "phone": "9876543210",
  "is_active": true
}
```

### 3.2 List Restaurants

```
GET /api/v1/restaurants/?area_id=...&city=Nagpur&cuisine=Chinese&skip=0&limit=100
```

All query params are optional.

**Response** `200` — array of restaurant objects (same shape as 3.1 response)

### 3.3 Get Restaurant by ID

```
GET /api/v1/restaurants/{restaurant_id}
```

**Response** `200` — single restaurant object  
**Response** `404` — `{"detail": "Restaurant not found"}`

### 3.4 Get Restaurant Menu

```
GET /api/v1/restaurants/{restaurant_id}/menu
```

**Response** `200`
```json
{
  "restaurant": {
    "restaurant_id": "e5f6g7h8-...",
    "restaurant_name": "Pranil Da Dhaba",
    "cuisine_type": ["North Indian"],
    "price_category": "mid-range"
  },
  "sections": [
    {
      "section_id": "s1s2s3s4-...",
      "section_name": "Biryani",
      "items": [
        {
          "item_id": "i1i2i3i4-...",
          "item_name": "Chicken Biryani",
          "description": "Aromatic basmati rice with tender chicken",
          "price": 320.00,
          "is_veg": false,
          "health_score": 6,
          "health_label": "moderate",
          "tags": ["spicy", "rice"]
        }
      ]
    }
  ]
}
```

---

## 4. Menu Upload

### 4.1 Upload Menu Image

```
POST /api/v1/menus/upload
Content-Type: multipart/form-data
```

**Form Fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | File | ✅ | Menu image (JPEG/PNG) |
| `area_name` | String | ✅ | e.g. "VR Mall" |
| `city` | String | ✅ | e.g. "Nagpur" |
| `restaurant_name` | String | ✅ | e.g. "Pranil Da Dhaba" |

**Flutter (Dart) Example**
```dart
var request = http.MultipartRequest('POST', Uri.parse('$baseUrl/menus/upload'));
request.files.add(await http.MultipartFile.fromPath('file', imagePath));
request.fields['area_name'] = 'VR Mall';
request.fields['city'] = 'Nagpur';
request.fields['restaurant_name'] = 'Pranil Da Dhaba';
var response = await request.send();
```

**Response** `200`
```json
{
  "upload_id": "u1u2u3u4-...",
  "status": "completed",
  "message": "Menu processed successfully",
  "restaurant_name": "Pranil Da Dhaba",
  "items_count": 44,
  "embedded_count": 44
}
```

**Response** `500` — `{"detail": "Processing failed: <reason>"}`

> ⚠️ This endpoint takes 10-30 seconds (OCR + LLM). Show a loading spinner.

### 4.2 Check Upload Status

```
GET /api/v1/menus/uploads/{upload_id}
```

**Response** `200`
```json
{
  "upload_id": "u1u2u3u4-...",
  "status": "completed",
  "restaurant_id": "e5f6g7h8-...",
  "image_path": "data/raw/menu_abc123.jpeg",
  "ocr_result": { ... },
  "structured_data": { ... },
  "error_message": null,
  "uploaded_at": "2026-03-20T12:00:00Z",
  "processed_at": "2026-03-20T12:00:25Z"
}
```

---

## 5. AI Chat (RAG)

### 5.1 Ask the Chatbot

```
POST /api/v1/chat
```

**Request Body**
```json
{
  "query": "healthy veg food under 200 rupees",
  "area_name": "VR Mall",       // optional — filters by area
  "restaurant_id": null          // optional — restrict to one restaurant
}
```

**Response** `200`
```json
{
  "answer": "If you're looking for healthy vegetarian options near VR Mall, I'd recommend the Dal Tadka at Pranil Da Dhaba for just ₹180 — it's a protein-rich lentil dish that's light on the stomach...",
  "items": [
    {
      "item_name": "Dal Tadka",
      "restaurant_name": "Pranil Da Dhaba",
      "section_name": "Veg Mains",
      "price": 180,
      "is_veg": true,
      "calories": 250,
      "health_score": 8,
      "similarity": 0.85
    }
  ],
  "filters_used": {
    "is_veg": true,
    "max_price": 200,
    "semantic_query": "healthy food"
  }
}
```

> ⚠️ This endpoint takes 3-8 seconds (embedding search + LLM). Show a loading spinner.

**Response** `400` — `{"detail": "Query cannot be empty."}`

---

## Error Format

All errors return:
```json
{ "detail": "Human-readable error message" }
```

Common HTTP status codes:
- `400` — Bad request (missing/invalid params)
- `404` — Resource not found
- `500` — Server error (check `detail` for reason)

---

## Notes for Flutter Integration

1. **No authentication required** — all endpoints are public
2. **CORS** — not relevant for native mobile apps (Android/iOS). Only matters for Flutter Web
3. **UUIDs** — all IDs are UUID v4 strings (e.g. `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`)
4. **Prices** — returned as numbers (float), not strings
5. **Null handling** — optional fields may be `null`, handle in Dart with `?` types
6. **Image access** — uploaded images available at `{base_url}/uploads/{filename}`
