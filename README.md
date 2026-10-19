# AssetWise

AssetWise is an enterprise-ready asset lifecycle management module for Odoo 19 Community. It provides a centralized register for company assets, controlled assignment and return workflows, preventive and corrective maintenance, depreciation estimates, operational reporting, and multi-company security.

## Highlights

- Centralized asset register with images, serial numbers, locations, vendors, warranties, and audit chatter.
- Automatic asset references using the `AST/YYYY/NNNNN` format.
- Controlled assignment and return workflow with concurrency protection.
- Preventive and corrective maintenance with lifecycle-aware asset status updates.
- Automatic corrective maintenance scheduling for damaged returns.
- Straight-line depreciation estimates with a configurable residual-value floor.
- Dashboard, list, kanban, graph, pivot, search, and grouped views.
- Filtered QWeb reports for inventory, assignment history, maintenance history, and depreciation.
- Viewer, Officer, and Administrator roles with backend-enforced permissions.
- Multi-company record isolation across all operational models.
- Demo data and a post-install automated test suite.

## Technology

- Odoo 19 Community
- PostgreSQL 17
- Python and XML/QWeb
- Docker Compose v2

AssetWise does not depend on Odoo Enterprise modules.

## Getting Started

### Prerequisites

- Docker Engine
- Docker Compose v2
- Git

### Installation

Clone the repository and enter the project directory:

```bash
git clone https://github.com/jayabelajar/assetwise.git
cd assetwise
```

Create the local environment file and start PostgreSQL:

```bash
cp .env.example .env
docker compose up -d db
```

Install AssetWise on a new Odoo database:

```bash
docker compose run --rm odoo odoo \
  --config=/etc/odoo/odoo.conf \
  --database=assetwise \
  --init=assetwise \
  --stop-after-init
```

Start the application:

```bash
docker compose up -d
```

Open [http://localhost:8069](http://localhost:8069), select the `assetwise` database, and sign in with the database administrator account.

> The bundled credentials are intended for local development only. Replace them before using AssetWise in a shared or production environment.

## Updating the Module

After pulling a newer revision, update the installed module with:

```bash
docker compose run --rm odoo odoo \
  --config=/etc/odoo/odoo.conf \
  --database=assetwise \
  --update=assetwise \
  --stop-after-init
```

Restart Odoo afterward:

```bash
docker compose restart odoo
```

## Access Roles

| Capability | Administrator | Officer | Viewer |
|---|:---:|:---:|:---:|
| View assets, dashboards, and reports | Yes | Yes | Yes |
| Create and edit assets | Yes | Yes | No |
| Assign and return assets | Yes | Yes | No |
| Manage maintenance work | Yes | Yes | No |
| Manage asset categories | Yes | No | No |
| Archive or dispose assets | Yes | No | No |

Assign roles from **Settings > Users & Companies > Users > Access Rights**. AssetWise roles are presented as an exclusive privilege selection in Odoo 19.

## Lifecycle

```text
Available --Assign--> Assigned --Return--> Available
    |                    |
    |                    +--Damaged return--> Corrective maintenance
    |
    +--Schedule maintenance--> Maintenance --Complete--> Available

Available --Administrator disposal--> Disposed
```

Lifecycle states cannot be edited directly. Workflow actions validate permissions and state transitions, while PostgreSQL constraints protect assignment and maintenance concurrency. Completed operational history cannot be deleted.

## Depreciation

AssetWise provides managerial straight-line estimates:

```text
annual depreciation = (acquisition cost - residual value) / useful life
accumulated depreciation = annual depreciation * elapsed days / 365
```

Elapsed time is capped at the configured useful life, and estimated book value never falls below the residual value. These calculations do not create accounting journal entries.

## Automated Tests

Run the post-install test suite against a disposable database:

```bash
docker compose run --rm odoo odoo \
  --config=/etc/odoo/odoo.conf \
  --database=assetwise_test \
  --init=assetwise \
  --test-tags=/assetwise \
  --stop-after-init \
  --log-level=test
```

The suite covers asset validation, workflow transitions, concurrency invariants, damaged returns, maintenance, depreciation, access control, multi-company isolation, immutable history, and QWeb report rendering.

Current verification result: **16 scenarios, 0 failures, 0 errors** on Odoo 19 with PostgreSQL 17.

## License

AssetWise is licensed under the [GNU Lesser General Public License v3.0](https://www.gnu.org/licenses/lgpl-3.0.html).
