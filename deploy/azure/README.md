# BankAI Azure demo deployment

This is a **single-VM educational deployment** of the existing BankAI stack. It keeps PostgreSQL, FastAPI, the evaluation worker, LiveKit, and the HTTPS web server on one Ubuntu VM. Plivo remains the external telephone provider. The VM's public HTTPS address replaces ngrok. This is a demo layout, not a high-availability bank deployment.

## Azure resources to review before creation

Create one resource group, one Ubuntu 24.04 LTS VM with **at least 8 GiB RAM** for the full stack and image builds, one static public IP with a DNS name label, an OS disk, and the VM's network security group. Check the price for your region and VM size in the [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/). Create a [budget alert](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets) before leaving the VM running. An alert notifies you; it does not stop billing automatically.

In the VM network security group, allow inbound TCP **80** and **443**, TCP **7881**, and UDP **7882**. Restrict SSH TCP **22** to your own IP. Keep PostgreSQL, FastAPI, and LiveKit port 7880 private. LiveKit documents the [WebRTC port roles](https://docs.livekit.io/transport/self-hosting/ports-firewall/). Azure's public IP [DNS name label](https://learn.microsoft.com/azure/virtual-machines/custom-domain) gives a hostname such as `bankai-demo.centralindia.cloudapp.azure.com`; use the exact hostname Azure assigns.

## Prepare the VM

The Azure deployment files must be committed and pushed to the GitHub branch you clone. They are currently local workspace changes; a fresh clone will not contain them until pushed. Never include any populated `.env` file in that commit.

1. Create the VM in the [Azure portal](https://portal.azure.com/) using an SSH key. Set the public IP to **Static**, assign its DNS name label, and record its public IP and full hostname. Do not create the VM until you have reviewed its monthly cost.
2. SSH into the VM. [Install Docker Engine and the Compose plugin](https://docs.docker.com/engine/install/ubuntu/) from Docker's official Ubuntu repository, then confirm `docker compose version` works.
3. Clone this repository on the VM. In the repository root, run:

   ```bash
   cp deploy/azure/example.env deploy/azure/.env
   chmod 600 deploy/azure/.env
   nano deploy/azure/.env
   ```

4. Fill `PUBLIC_HOST` with the Azure hostname and `AZURE_PUBLIC_IP` with the static IP. Generate a fresh `APP_SECRET_KEY`, a long URL-safe `POSTGRES_PASSWORD`, and LiveKit keys. Put the **same** database password in `DATABASE_URL`. Add a working Gemini key and model. Keep `VOICE_ENABLED=false` and `PHONE_ENABLED=false` during the first boot. Never copy the local `.env` to the VM; it contains local settings and keys that have previously been shared in chat. Rotate those provider keys before cloud use.

The populated `deploy/azure/.env` is ignored by Git. Never paste it into chat, a command log, or a commit.

## Start and initialize

From the repository root on the VM:

```bash
docker compose --env-file deploy/azure/.env -f deploy/azure/compose.yaml config -q
docker compose --env-file deploy/azure/.env -f deploy/azure/compose.yaml up -d --build
docker compose --env-file deploy/azure/.env -f deploy/azure/compose.yaml exec backend python -m alembic upgrade head
docker compose --env-file deploy/azure/.env -f deploy/azure/compose.yaml exec backend python -m app.seed.demo_data
curl -fsS "https://YOUR_AZURE_HOSTNAME/ready"
```

The last command should return `{"status":"ready","database":"connected"}`. Caddy obtains and renews the public HTTPS certificate when DNS points to the VM and ports 80/443 are reachable. The React app is served as a production build. The `/rtc` WebSocket path goes to LiveKit; `/api` and `/ready` go to FastAPI. Plivo webhooks also use `/api` and are signature-checked by BankAI.

## Create the owner and enable features

1. Create the owner privately inside the backend container. The command asks for the name, email, and a password without echoing the password. Save the printed customer ID in your private notes:

   ```bash
   docker compose --env-file deploy/azure/.env -f deploy/azure/compose.yaml exec backend python -m app.seed.cloud_owner
   ```

2. Edit `deploy/azure/.env`: set `PHONE_OWNER_CUSTOMER_ID` and `EVALUATION_OWNER_CUSTOMER_ID` to that owner ID. Add rotated Plivo credentials, the approved destination and caller numbers, then set `PHONE_ENABLED=true` if you want telephone calling. Set `VOICE_ENABLED=true` if you want browser voice. Keep `EVALUATION_LIVE_ENABLED=false` until you intend to run paid model comparisons.
3. Recreate backend and worker with the new settings, then seed the owner's fictional records:

   ```bash
   docker compose --env-file deploy/azure/.env -f deploy/azure/compose.yaml up -d --force-recreate backend evaluation-worker
   docker compose --env-file deploy/azure/.env -f deploy/azure/compose.yaml exec backend python -m app.seed.owner_demo
   ```

4. If policy answers are required, run `python -m app.services.policies` inside the backend container **once** after reviewing Gemini embedding usage. It makes provider calls for new or changed policy sections.
5. Verify the web pages and text assistant first, then browser voice. For Plivo, check that `https://YOUR_AZURE_HOSTNAME/ready` works from the backend and that your configured Plivo number can place calls to the approved test recipient. The call is a real, potentially billable call.

The seeded Asha/Ravi/Mira profiles remain available to agents and evaluations, but their published sample passwords cannot log in when `APP_ENV=cloud_demo`. The owner logs in with their own password. Public registration remains disabled.

## Operation and limits

- `docker compose --env-file deploy/azure/.env -f deploy/azure/compose.yaml ps` shows container status.
- `docker compose --env-file deploy/azure/.env -f deploy/azure/compose.yaml logs --tail=100 backend web livekit` shows recent service errors. Do not share logs before checking for personal data.
- Back up the PostgreSQL volume before updates. This single VM has no automatic failover; an OS disk or VM loss can lose demo data without a backup.
- To stop VM compute charges, **Stop (deallocate)** it in Azure, not just `shutdown` inside Ubuntu. Azure says [disks and networking can still incur charges](https://learn.microsoft.com/azure/virtual-machines/states-billing) when the VM is deallocated.

No Azure resource is created by the files in this folder. Deployment requires an Azure subscription, VM creation, a hostname, and fresh private credentials.
