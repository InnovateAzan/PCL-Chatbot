# PCL GPT SPFx

This SPFx Application Customizer injects the floating PCL GPT widget onto the
Pakistan Cables One Desk SharePoint page.

## What it loads

- hosted loader script: `sharepoint-loader.js`
- hosted embed panel: `embed.html`
- hosted backend API over `https`

## Before you build

Replace the placeholder host URLs in these files:

- [config/serve.json](/D:/PROJECT/Chart%20Bot/sharepoint-spfx/config/serve.json)
- [sharepoint/assets/elements.xml](/D:/PROJECT/Chart%20Bot/sharepoint-spfx/sharepoint/assets/elements.xml)

Use your real hosted URLs, for example:

```text
https://chat.internal.example.com/sharepoint-loader.js
https://chat.internal.example.com/embed.html?apiBase=https%3A%2F%2Fchat.internal.example.com%2Fapi
```

## Build commands

```powershell
npm install
npm run build
npm run package
```

The packaged app will be created at:

```text
sharepoint-spfx/sharepoint/solution/pcl-gpt.sppkg
```

## Deploy idea

Upload the `.sppkg` file to the SharePoint App Catalog, then add the
Application Customizer to the One Desk site.
