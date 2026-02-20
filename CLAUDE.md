# FunnelForge Project Notes

## Default Template for New Users
- The template named **"FF Template Example"** should be the default template that loads for all first-time users.
- This was created by the developer as the standard starting template for the app.

## Key Architecture
- Main app: `funnel_forge/app.py`
- HTML formatting/toolbar: `funnel_forge/html_format.py`
- Styles/constants: `funnel_forge/styles.py`
- Email sending core: `funnelforge_core.py`
- Signature file: `%LOCALAPPDATA%\Funnel Forge\signature.txt`
- Config: `%LOCALAPPDATA%\Funnel Forge\funnelforge_config.json`
- Campaigns: `%LOCALAPPDATA%\Funnel Forge\Campaigns\`
- Templates: `%LOCALAPPDATA%\Funnel Forge\Templates\`

## File Sizes (context budget guide)
- `app.py` — 20,492 lines (NEVER read in full; use line ranges below)
- `html_format.py` — 1,345 lines
- `styles.py` — 1,042 lines
- `ui_components.py` — 705 lines
- `funnelforge_core.py` — 878 lines

## app.py Navigation Map
**Helper classes (L167–L999):**
- ToolTip: L167–L237
- AutoHideVScrollbar: L239–L311
- ContactsTableWindow: L313–L467
- AttachmentManagerWindow: L469–L652
- OneTimeContactsImportedDialog: L654–L741
- ToastNotification: L743–L881
- ThemedInputDialog: L883–L999
- EditSignatureWindow: L1001–L1215

**FunnelForgeApp (L1217–L20492) — key sections:**
- `__init__` / startup: L1218–L1565
- Startup wizard: L1657–L1937
- Registration dialog: L1951–L2216
- Build styles: L2250–L2423
- Build header/nav: L2424–L2666
- Screen switching: L2748–L2826
- AI chat / campaign gen: L2883–L3242
- Campaign load/save/manage: L3243–L3464
- Dashboard: L5154–L5457
- Build emails screen: L5753–L5806
- Sequence/schedule screen: L5807–L5904
- Campaign save/open: L6029–L7423
- Stay Connected: L6310–L7075
- Nurture campaigns: L6464–L6911
- Contacts screen: L7424–L7986
- Validation: L8027–L8137
- Execute/review panel: L8138–L13500
- Status bar / layout: L13501–L13664
- Email tab management: L13665–L13757
- Email editor build: L13825–L13914
- Templates: L13944–L14860
- Email tab creation: L14861–L15077
- Schedule panel: L15188–L15699
- Contacts card (sequence page): L16009–L16619
- Tools card: L16620–L16943
- Signature: L16944–L17202
- Date/time/schedule logic: L17203–L17795
- Preset sequences: L17796–L17992
- Add/delete emails: L17993–L19135
- Preview & send: L19334–L19551
- Cancel/config/save: L19552–L19931
- Run sequence (email execution): L20127–L20472
- launch_main: L20473–L20492

## Design Decisions
- Signature is read-only in the email editor; only editable via "Add/Edit Signature" dialog
- Signature preview widget sits below each email body editor (disabled tk.Text, muted color)
- Toolbar uses canvas-drawn icons (not tk.Button) for consistent styling
- Email HTML uses two-pass serialization (flatten segments into lines, then generate HTML)
- Inline CSS on list elements (ul/ol/li) to prevent Outlook spacing issues
