# LinkedIn drafts

## Projects entry

**Name**
FactoryIQ — Manufacturing Intelligence & Quality Management System

**Description**
I scoped FactoryIQ as an AI-assisted engineering portfolio project for a fictional manufacturing plant. The application combines equipment, stock reservations, quality inspections, maintenance, corrective actions and sorter simulation telemetry in PostgreSQL, with a FastAPI API and a React dashboard. It uses SQL transactions and row locks for stock control, and validates and deduplicates sorter CSV imports. The project suite passed 16 PostgreSQL integration tests and six Chromium workflow tests. Codex authored the initial implementation and ran the reported tests. The repo includes a guide for reproducing the results and reviewing the underlying SQL and transaction logic.

**Skills**
PostgreSQL · SQL · Python · React.js · Software Testing

**Media**
Upload `dashboard.png` and `supplier-quality.png` from the deliverables. Add the verified [portfolio](https://fahad-chohan-engineering.naturalstar2.chatgpt.site) and [GitHub repository](https://github.com/S4mos4/factoryiq-manufacturing-system) as links after the FactoryIQ portfolio feature is live and the repository is public. The current GitHub link is private.

## Announcement post

I scoped FactoryIQ, an AI-assisted portfolio project for manufacturing intelligence and quality management. I wanted to explore how a plant could use the same system to track equipment downtime, reserve parts, record inspection results, and prioritize maintenance.

FactoryIQ uses PostgreSQL, FastAPI and React. Its inventory workflow uses a row lock and a transaction to keep concurrent requests from claiming the same last unit. The CSV adapter also reads traces from my warehouse sorter simulation and turns lane events into jam and downtime records.

The automated suite passed 16 PostgreSQL integration tests and six Chromium workflows. In a benchmark with 205,000 synthetic events, a partial index reduced median execution for one machine-filtered fault query from 1.260 ms to 0.045 ms.

I defined the project scope. Codex authored the initial implementation and ran these checks. My next step is to reproduce the concurrency test and modify the SQL queries so I can explain the trade-offs in an interview. The demo runs with synthetic data and software simulation.

Portfolio
https://fahad-chohan-engineering.naturalstar2.chatgpt.site

Source
https://github.com/S4mos4/factoryiq-manufacturing-system

## Add the entry manually

1. On LinkedIn desktop, open **Me → View Profile → Add profile section → Recommended → Add projects**.
2. Paste the project name and description. Add the five skills. Use **Add media** to upload the two screenshots and **Add a link** for each approved URL.
3. Save the Projects entry after reviewing its visibility and the media. [LinkedIn Projects help](https://www.linkedin.com/help/linkedin/answer/a8064614)
4. On the Feed, choose **Start a post**, paste the announcement, and add the dashboard photo. Add the supplier screenshot if desired. For a photo post, keep URLs in the body as plain text and use the photos as the media.
5. Use **ALT** to describe the dashboard. Suggested text is “FactoryIQ operations overview showing equipment count, machine availability, downtime, defect rates and a downtime chart for synthetic manufacturing data.” Review audience settings before posting. [LinkedIn posting help](https://www.linkedin.com/help/linkedin/answer/a528176) · [Photo help](https://www.linkedin.com/help/linkedin/answer/a527229)

Update the final paragraph once you personally reproduce tests or make changes. Direct posting requires authorized LinkedIn access and publication approval.
