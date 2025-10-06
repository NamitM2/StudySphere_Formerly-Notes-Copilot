# Alternative Color Schemes for Notes Copilot

## Current: Emerald + Purple
- **Primary**: Emerald (#10b981, #059669)
- **Secondary**: Purple (#a855f7, #9333ea)
- **Background**: Black/Zinc

---

## Option 1: Ocean Blue + Coral
**Modern, Professional, Energetic**
- **Primary (Notes)**: Ocean Blue (#0ea5e9, #0284c7) - sky-500, sky-600
- **Secondary (Knowledge)**: Coral/Orange (#f97316, #ea580c) - orange-500, orange-600
- **Background**: Black/Zinc
- **Vibe**: Professional with a warm pop, great contrast

### Tailwind Classes:
```jsx
// From Notes: sky-500, sky-600, sky-950
// Model Knowledge: orange-500, orange-600, orange-950
```

---

## Option 2: Cyan + Pink/Magenta
**Vibrant, Modern, Tech-Forward**
- **Primary (Notes)**: Cyan (#06b6d4, #0891b2) - cyan-500, cyan-600
- **Secondary (Knowledge)**: Pink/Magenta (#ec4899, #db2777) - pink-500, pink-600
- **Background**: Black/Zinc
- **Vibe**: Bold, modern, high energy

### Tailwind Classes:
```jsx
// From Notes: cyan-500, cyan-600, cyan-950
// Model Knowledge: pink-500, pink-600, pink-950
```

---

## Option 3: Teal + Amber
**Balanced, Sophisticated, Warm**
- **Primary (Notes)**: Teal (#14b8a6, #0d9488) - teal-500, teal-600
- **Secondary (Knowledge)**: Amber (#f59e0b, #d97706) - amber-500, amber-600
- **Background**: Black/Zinc
- **Vibe**: Sophisticated with warmth, easy on eyes

### Tailwind Classes:
```jsx
// From Notes: teal-500, teal-600, teal-950
// Model Knowledge: amber-500, amber-600, amber-950
```

---

## Option 4: Indigo + Rose
**Elegant, Premium, Balanced**
- **Primary (Notes)**: Indigo (#6366f1, #4f46e5) - indigo-500, indigo-600
- **Secondary (Knowledge)**: Rose (#f43f5e, #e11d48) - rose-500, rose-600
- **Background**: Black/Zinc
- **Vibe**: Premium feel, elegant contrast

### Tailwind Classes:
```jsx
// From Notes: indigo-500, indigo-600, indigo-950
// Model Knowledge: rose-500, rose-600, rose-950
```

---

## Option 5: Violet + Lime
**Bold, Unique, High Contrast**
- **Primary (Notes)**: Violet (#8b5cf6, #7c3aed) - violet-500, violet-600
- **Secondary (Knowledge)**: Lime (#84cc16, #65a30d) - lime-500, lime-600
- **Background**: Black/Zinc
- **Vibe**: Unique, bold, stands out

### Tailwind Classes:
```jsx
// From Notes: violet-500, violet-600, violet-950
// Model Knowledge: lime-500, lime-600, lime-950
```

---

## Option 6: Blue + Yellow
**Classic, Accessible, High Contrast**
- **Primary (Notes)**: Blue (#3b82f6, #2563eb) - blue-500, blue-600
- **Secondary (Knowledge)**: Yellow (#eab308, #ca8a04) - yellow-500, yellow-600
- **Background**: Black/Zinc
- **Vibe**: Classic, highly accessible, clear distinction

### Tailwind Classes:
```jsx
// From Notes: blue-500, blue-600, blue-950
// Model Knowledge: yellow-500, yellow-600, yellow-950
```

---

## How to Change Color Scheme

### Quick Find & Replace in App.jsx:

**From Current (Emerald + Purple):**
- `emerald-` → Replace with new primary color
- `purple-` → Replace with new secondary color

**Example: To switch to Ocean Blue + Coral:**
1. Find: `emerald-` → Replace: `sky-`
2. Find: `purple-` → Replace: `orange-`

### Key Places to Update:
1. Header logo gradient
2. All section headings
3. Button gradients
4. Answer box backgrounds/borders
5. Tags (From Notes / Model Knowledge)
6. Focus rings on inputs

---

## Recommended: Ocean Blue + Coral (Option 1)
This provides the best balance of:
- **Professionalism** - Blue is trusted and familiar
- **Energy** - Coral adds warmth without being overwhelming
- **Contrast** - Excellent visual distinction between note-based and AI knowledge
- **Accessibility** - High contrast ratios for readability
