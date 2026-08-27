# DocMind

Cloud-native semantic document search engine with AI-powered question answering.
Senior Project — Faisal Alrabiah — Software Engineering Capstone.

## Repo Structure

```
docmind/
├── infra/                  # Terraform infrastructure-as-code
│   ├── modules/             # Reusable Terraform modules (storage, search, aks, etc.)
│   └── environments/dev/    # Dev environment root config (backend, variables, main)
├── backend/                 # FastAPI backend services
│   ├── app/                  # Application source
│   └── tests/                 # Unit + integration tests
├── frontend/                # React + TypeScript web app
│   ├── src/
│   └── public/
├── .github/workflows/       # CI/CD pipeline definitions
└── docs/                    # Architecture diagrams, ADRs, deployment guide
```

## Week 1 Setup Checklist

- [x] Azure subscription created, $200 free credit claimed
- [ ] Resource group created (`docmind-rg`)
- [ ] Terraform state storage account created
- [ ] `infra/environments/dev/backend.tf` updated with your storage account name
- [ ] `terraform init` run successfully
- [ ] Repo pushed to GitHub

## Getting Started

### 1. Configure Terraform backend

Edit `infra/environments/dev/backend.tf` and replace `REPLACE_WITH_YOUR_TFSTATE_SA_NAME`
with the storage account name you created via Azure CLI.

### 2. Initialize Terraform

```bash
cd infra/environments/dev
terraform init
terraform plan
```

### 3. Backend (added in Week 3+)

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 4. Frontend (added in Week 7+)

```bash
cd frontend
npm install
npm run dev
```

## Architecture

See `docs/architecture.md` for the full system diagram and data flow.

## License

Academic project — Senior Capstone.
