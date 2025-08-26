# AI Voice Demo
Listen Lambda (SAM + FastAPI)

Setup
- Create secret for ElevenLabs API key:
  aws secretsmanager create-secret --name ELEVENLABS_API_KEY --secret-string 'YOUR_KEY'

Deploy
- sam build && sam deploy --guided

Health check
- curl "$API_URL/health"

Update origins
- sam deploy --parameter-overrides ALLOWED_ORIGINS="https://localhost,https://your-site.com"
