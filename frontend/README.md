# Frontend — decision pending

The team needs to choose between React (Vercel) and Flutter before scaffolding.

| Criteria | React (Vercel) | Flutter |
|---|---|---|
| Demo for judges | Direct web link, zero friction | APK to install, or a video needed |
| Camera access (front/side photos) | OK via browser (getUserMedia) | Native, smoother |
| Team experience | Already used on the previous hackathon | Used on Geya |
| Deployment | Vercel, zero-config | Less direct for web |

Once decided:
- **React**: `npx create-vite@latest . -- --template react`, add Tailwind, update
  `.kiro/steering/tech.md`.
- **Flutter**: `flutter create .`, update `.kiro/steering/tech.md`.

Either way, write the spec in `.kiro/specs/frontend-ui/` first, before having Kiro generate
the screens.
