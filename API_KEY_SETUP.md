# Multiple API Keys Setup - Automatic Fallback

The system now supports **multiple Gemini API keys with automatic fallback** when quota limits are hit!

## How It Works

When the primary API key hits its quota limit (429 error), the system **automatically switches** to the next available key. This gives you:
- **5x more requests** with 5 keys = 250 requests/day instead of 50
- **Zero downtime** - seamless failover
- **Automatic recovery** - cycles through all keys

## Environment Variables Setup

### **Local Development (.env file):**

```bash
# Primary key
GOOGLE_API_KEY="your-primary-key-here"

# Backup keys (optional - add as many as you need, up to 5)
GOOGLE_API_KEY_1="your-backup-key-1"
GOOGLE_API_KEY_2="your-backup-key-2"
GOOGLE_API_KEY_3="your-backup-key-3"
GOOGLE_API_KEY_4="your-backup-key-4"
GOOGLE_API_KEY_5="your-backup-key-5"
```

### **Production (Render Environment Variables):**

Add these in your Render dashboard under **Environment**:

| Variable | Value |
|----------|-------|
| `GOOGLE_API_KEY` | `your-primary-key` |
| `GOOGLE_API_KEY_1` | `your-backup-key-1` |
| `GOOGLE_API_KEY_2` | `your-backup-key-2` |
| `GOOGLE_API_KEY_3` | `your-backup-key-3` |
| etc. | ... |

## How Fallback Works

1. **Start**: Uses `GOOGLE_API_KEY` (primary)
2. **Quota hit**: Automatically switches to `GOOGLE_API_KEY_1`
3. **Quota hit**: Switches to `GOOGLE_API_KEY_2`
4. **Continues**: Cycles through all available keys
5. **All exhausted**: Returns error (wait for quota reset)

## Quota Limits

**Free Tier per API key:**
- 50 requests per day
- Resets at midnight UTC

**With 6 keys:**
- 300 requests per day total
- System automatically manages rotation

## Getting Multiple API Keys

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Click **"Create API Key"**
3. Copy the key
4. Repeat 5 times (you can create up to 5 keys per account)
5. Add all keys to your environment


Testing

The system will log to console when switching keys:

```
API key 1 quota exceeded, trying next key...
API key 2 quota exceeded, trying next key...
```

You'll see which key is active in the logs!

## Quick Setup Example

```bash
# .env file
GOOGLE_API_KEY="AIza...key1"
GOOGLE_API_KEY_1="AIza...key2"
GOOGLE_API_KEY_2="AIza...key3"

# Now your app has 150 requests/day instead of 50!
```

---

