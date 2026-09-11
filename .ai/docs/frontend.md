# Frontend (api/static/index.html)

Single HTML file, no build step, no framework. Dark theme, Bootstrap Icons, vanilla JS.

## File Manager

- Click any image card → opens `#mMediaEditor` modal (two-column: image left 380px fixed, form right flex:1)
- Edit panel: prompt textarea, reference images, usage chain (`<details>`), generation parameters (safety, quality, aspect ratio, format)
- **Tag system**: tags stored as JSON on `PostMedia.tags`; tag chips shown on each file card; tag filter bar above the grid; `GET /api/media/tags` populates a global `_mmeAllTags` array used for custom autocomplete dropdown (NOT native `<datalist>` — custom `<div id="mmeTagAc">` positioned above the input using `bottom:calc(100% + 2px)`, filtering `_mmeAllTags` on every keystroke)
- **Usage chain**: `GET /api/media/library/{filename}/usage` → shows where image is used; supports removing references and opening the post that uses it
- Upload button: `POST /api/media/library/upload`
- `#mMediaEditor` container uses `height:88vh;display:flex;flex-direction:row` — do NOT add `.m-box` class (it hardcodes `flex-direction:column` and breaks the two-column layout)

## Character profile management

- Basic tab: `profile_bio` textarea, profile picture upload + gallery picker, circular preview
- Social tab: "Push Profile to Platforms" buttons (Instagram, X/Twitter)
- `#mProfilePicPicker` modal: grid of character's generated images (`GET /api/characters/{id}/generated-images`)
