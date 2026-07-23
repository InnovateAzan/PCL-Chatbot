# SharePoint One Desk Setup

This project now includes two SharePoint-friendly frontend assets:

- [frontend/embed.html](/D:/PROJECT/Chart%20Bot/frontend/embed.html) for an iframe-safe chat panel
- [frontend/sharepoint-loader.js](/D:/PROJECT/Chart%20Bot/frontend/sharepoint-loader.js) for a floating launcher and panel on the page
- [sharepoint-spfx/](/D:/PROJECT/Chart%20Bot/sharepoint-spfx) for an SPFx Application Customizer scaffold

## Important limitation

Your One Desk page is loaded from `https://pakistancable.sharepoint.com`, so it cannot safely call a local backend like `http://127.0.0.1:8001`.

That combination is blocked by the browser because:

- SharePoint is `https`
- your local chatbot API is `http`
- modern browsers block mixed-content requests from secure pages to insecure APIs

So for SharePoint preview or production, host the chatbot frontend and backend on an internal `https` URL first.

## Quick preview path

1. Host the `frontend/` folder on an internal HTTPS URL.
2. Put the FastAPI backend behind HTTPS as well.
3. Point the embed page to your HTTPS API using the `apiBase` query parameter.
4. Load the widget on the SharePoint page through SPFx or another approved script-injection method.

Example embed URL:

```text
https://your-chat-host.example.com/embed.html?apiBase=https%3A%2F%2Fyour-chat-host.example.com%2Fapi
```

Example loader snippet:

```html
<script
  src="https://your-chat-host.example.com/sharepoint-loader.js"
  data-embed-url="https://your-chat-host.example.com/embed.html?apiBase=https%3A%2F%2Fyour-chat-host.example.com%2Fapi"
  data-width="460"
  data-height="720"
  data-open="true"
></script>
```

## Recommended One Desk approach

For a real SharePoint rollout, use an SPFx Application Customizer.

Why this is the best fit:

- it can inject the floating launcher on every One Desk page
- it works with modern SharePoint governance better than ad-hoc script injection
- it keeps the UI attached to the current page instead of placing it inside a normal web part region

The scaffold is now available here:

- [sharepoint-spfx/src/extensions/pclGpt/PclGptApplicationCustomizer.ts](/D:/PROJECT/Chart%20Bot/sharepoint-spfx/src/extensions/pclGpt/PclGptApplicationCustomizer.ts)
- [sharepoint-spfx/config/serve.json](/D:/PROJECT/Chart%20Bot/sharepoint-spfx/config/serve.json)
- [sharepoint-spfx/sharepoint/assets/elements.xml](/D:/PROJECT/Chart%20Bot/sharepoint-spfx/sharepoint/assets/elements.xml)

## Backend configuration

The backend now supports:

- `FRONTEND_ORIGIN`
- `SHAREPOINT_ORIGIN`
- `ADDITIONAL_ALLOWED_ORIGINS`

For Pakistan Cables One Desk, set `SHAREPOINT_ORIGIN` to:

```text
https://pakistancable.sharepoint.com
```

If your hosted embed page lives on another HTTPS origin, add that host to:

```text
ADDITIONAL_ALLOWED_ORIGINS=https://your-chat-host.example.com
```

## Practical next step

If you want, the next implementation step is to create the SPFx Application Customizer package that loads `sharepoint-loader.js` directly on One Desk.
