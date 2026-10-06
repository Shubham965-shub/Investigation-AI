# InvestigationAI QA Automation

Selenium UI automation for the InvestigationAI frontend.

## Prerequisites

- Java 17+
- Maven 3.9+
- InvestigationAI running locally (`docker compose up --build` from the repository root)

## Run tests

```bash
mvn test
```

Run sanity checks (login page availability only):

```bash
mvn test -Dsurefire.suiteXmlFiles=sanity.xml
```

With environment-backed credentials:

```bash
QA_USERNAME="your-username" QA_PASSWORD="your-password" \
mvn test -Dsurefire.suiteXmlFiles=sanity.xml -Dheadless=true
```

Run the smoke suite (valid login and dashboard availability):

```bash
QA_USERNAME="your-username" QA_PASSWORD="your-password" \
mvn test -Dsurefire.suiteXmlFiles=smoke.xml -Dheadless=true
```

The Cucumber login scenario is implemented by `LoginSteps.java` and runs with:

```bash
QA_USERNAME="your-username" QA_PASSWORD="your-password" \
mvn test -Dtest=TestRunner -Dheadless=true
```

Run the deployed Athena dashboard feature:

```bash
QA_USERNAME="your-username" QA_PASSWORD="your-password" \
mvn test -Dtest=TestRunner \
	-DbaseUrl=https://athena.strideslighthouse.com \
	-Dheadless=true
```

The dashboard feature is `src/test/resources/features/dashboard.feature`, and its Java steps are in `DashboardSteps.java`.

Override settings without editing committed files:

```bash
mvn test -Dbrowser=firefox -Dheadless=true -DbaseUrl=http://localhost:5173
```

The HTML report is generated at `target/extent-report.html` after every TestNG run.
The Excel test-case report is generated at `target/login-test-cases.xlsx` after every TestNG run.

Run against Selenium Grid instead of a local browser:

```bash
mvn test -Dexecution=grid -DgridUrl=http://localhost:4444/wd/hub -Dbrowser=chrome -Dheadless=true
```

Start a local Selenium Grid with Docker:

```bash
docker run --rm -d --name selenium-grid -p 4444:4444 -p 7900:7900 selenium/standalone-chrome:latest
```

Use the requested Hub and browser-node topology:

```bash
docker compose -f docker-compose.selenium.yml up -d
```

Run on the Grid from the host:

```bash
mvn test -Dexecution=grid -DgridUrl=http://localhost:4444/wd/hub \
	-DbaseUrl=http://host.docker.internal:5173 -Dbrowser=chrome -Dheadless=true
```

Cucumber runs from `src/test/resources/features` and writes `target/cucumber-report.html`.

Grid UI/VNC is available at `http://localhost:7900`.

Set credentials through environment variables:

```bash
export QA_USERNAME="your-username"
export QA_PASSWORD="your-password"
mvn test
```

The default values are defined in `src/test/resources/config/config.properties`.

## Multiple users and screenshots

Add one user per row in `src/test/resources/test-data/users.csv`:

```csv
username,password
${QA_USERNAME},${QA_PASSWORD}
user.two@example.com,password456
```

The CSV is ignored by Git because it contains credentials. `${QA_USERNAME}` and `${QA_PASSWORD}` resolve from the terminal environment. Add more rows for additional users. The data-driven test is `successfulLoginForConfiguredUser`.
Screenshots for failed tests are saved under `target/screenshots/`.
