# 🚀 Frontend Integration Guide: Menu Intelligence API

This guide details exactly how the frontend should connect to the FastAPI backend, how authentication works, and the exact data models to expect (including the notorious `.city` field!).

---

## 1. Authentication Flow (Very Important)

The backend now has **Strict Ownership Verification**. 
You must use Supabase for authentication on the frontend, but you MUST pass the Supabase JWT token to the Python backend so it knows who is making the request.

### The Flow:
1. **User logs in on Frontend** using Supabase SDK (`supabase.auth.signInWithPassword()`).
2. **Get the Session Token**: Extract the `access_token` from the Supabase session.
3. **Call the Python Backend**: Attach the token to **EVERY** protected API request in the headers:
   ```javascript
   // Example Axios/Fetch configuration
   const headers = {
     "Authorization": `Bearer ${supabase_access_token}`,
     "Content-Type": "application/json"
   };
   ```

> [!WARNING]
> Without the `Authorization` header, the backend will reject your requests with a `401 Unauthorized` or `403 Forbidden`.

---

## 2. Core Data Models

### The Restaurant Object (Pay attention to `city` and `area_name`)
When you fetch a restaurant from the backend, this is the exact shape of the JSON you will receive. Note that **`city` is provided at the root level**!

```typescript
interface Restaurant {
  restaurant_id: string;      // UUID
  owner_id: string | null;    // UUID (Null if public data)
  restaurant_name: string;
  cuisine_type: string[];     // e.g., ["Indian", "Chinese"]
  price_category: string;     // e.g., "mid-range"
  address: string;
  phone: string;
  area_id: string;
  area_name: string;          // Extracted from Area table (e.g., "VR Mall")
  city: string;               // Extracted from Area table (e.g., "Nagpur")
  is_active: boolean;
}
```
*💡 **Frontend Dev Note:** Do not remove `.city` from your UI! Ensure your TypeScript/Dart models properly parse it from the root of this JSON response.*

---

## 3. Endpoints Step-by-Step

**Base API URL:** `http://localhost:8000/api/v1`

### Step 1: Check if User is Logged In & Owns a Restaurant
Call this immediately after the user logs in via Supabase to decide if they should see the "Create Restaurant" screen or be redirected to their Dashboard.

**`GET /auth/me`**
- **Auth required?** ✅ Yes
- **Response:**
  ```json
  {
    "user_id": "uuid-of-user",
    "email": "user@example.com",
    "restaurant_id": "uuid-here-if-they-own-one-else-null",
    "restaurant_name": "Name-if-they-own-one-else-null"
  }
  ```

---

### Step 2: Creating a Restaurant (Initial Onboarding)
If `restaurant_id` was `null` in Step 1, hit these endpoints to create one.

1. **Get Cities:** `GET /areas/cities` (No Auth) -> Returns `["Nagpur", "Mumbai"]`
2. **Get Areas by City:** `GET /areas/?city=Nagpur` (No Auth) -> Returns List of Areas.
3. **Create the Restaurant:** 
   **`POST /restaurants/`**
   - **Auth required?** ✅ Yes (The user's token proves who they are)
   - **Body:**
     ```json
     {
       "restaurant_name": "My Food Place",
       "area_id": "uuid-selected-from-step-2",
       "cuisine_type": ["Italian"],
       "price_category": "high-end",
       "address": "123 Main St",
       "phone": "9998887776"
     }
     ```
   *(Note: You do NOT send `owner_id`. The backend extracts it from the Bearer token securely).*

---

### Step 3: Uploading the Menu Image (OCR Pipeline)
Once the restaurant exists, the user uploads their menu image.

**`POST /admin/restaurants/{restaurant_id}/menu/upload`**
- **Auth required?** ✅ Yes (Must be the owner)
- **Content-Type**: `multipart/form-data`
- **Fields:**
  - `file`: The image file (JPEG, PNG).
  - `mode`: `"replace"` (clears old menu) OR `"append"` (adds to existing).

*(This takes 10-30 seconds. Show a loading spinner!)*

---

### Step 4: The Admin Dashboard
Endpoints for viewing stats and managing items.

1. **Dashboard Stats:**
   **`GET /admin/dashboard/{restaurant_id}`** (✅ Auth required)
   Returns item counts, average prices, veg/non-veg splits.

2. **List Menu Items (Table View):**
   **`GET /admin/restaurants/{restaurant_id}/items`** (✅ Auth required)
   Returns an array of `MenuItemSummary` objects. (Can filter via query params `?is_veg=true` or `?section_name=Pizza`).

3. **Edit a Menu Item:**
   **`PUT /admin/restaurants/{restaurant_id}/items/{item_id}`** (✅ Auth required)
   Pass only the fields you want to update (e.g., `{"price": 400.00}`).

4. **Delete an Item:**
   **`DELETE /admin/restaurants/{restaurant_id}/items/{item_id}`** (✅ Auth required)

---

### Step 5: Public Consumer View
When standard users (not admins) view the restaurant or use the food AI chat, they do NOT need to be logged in.

- **Get All Restaurants:** `GET /restaurants/` (No Auth)
- **Get Full Menu tree:** `GET /restaurants/{restaurant_id}/menu` (No Auth)
- **AI Chatbot:** `POST /chat/` (No Auth)

---

## 4. Troubleshooting Cheat Sheet for Frontend
| If you see... | It means... |
|---------------|-------------|
| **401 Unauthorized** | You didn't send the `Authorization: Bearer <token>` header, or the token expired. |
| **403 Forbidden** | You sent a valid token, but that user does NOT own the `restaurant_id` you tried to modify. |
| **404 Not Found** | The `restaurant_id` or `area_id` you sent literally doesn't exist in the database. |
| **409 Conflict** | You tried to create a Restaurant, but this user already owns one (1-to-1 rule). |
| **`.city` is undefined** | The frontend TypeScript/Dart model needs to be updated to accept `city` at the root of the restaurant object. |
