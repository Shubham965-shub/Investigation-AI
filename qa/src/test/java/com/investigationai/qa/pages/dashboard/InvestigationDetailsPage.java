package com.investigationai.qa.pages.dashboard;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.openqa.selenium.By;
import org.openqa.selenium.JavascriptExecutor;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.Select;
import org.openqa.selenium.support.ui.WebDriverWait;

public class InvestigationDetailsPage {

    private static final By DETAILS_TITLE = By.xpath("//h2[normalize-space()='Investigation Details']");
    private static final By DETAILS_SECTION = By.xpath(
            "//h2[normalize-space()='Investigation Details']/ancestor::div[contains(@class,'ac-card')][1]");
    private static final By LIST_ROWS = By.cssSelector("table.ac-table tbody tr.ac-inv-row:not(.ac-inv-subrow)");
    private static final By LIST_VIEW = By.cssSelector("button[aria-label='List view']");
    private static final By CARD_VIEW = By.cssSelector("button[aria-label='Card view']");
    private static final By PREVIEW_PANEL = By.cssSelector("div[role='dialog'][aria-hidden='false']");
    private static final By START_DATE = By.cssSelector("input[type='date'][title*='Only show investigations']");
    private static final By SHOW_ALL_DATES = By.xpath(
            "//h2[normalize-space()='Investigation Details']/ancestor::div[contains(@class,'ac-card')][1]//button[normalize-space()='Show all dates']");

    private final WebDriver driver;
    private final WebDriverWait wait;

    public InvestigationDetailsPage(WebDriver driver) {
        this.driver = driver;
        wait = new WebDriverWait(driver, Duration.ofSeconds(30));
        wait.until(ExpectedConditions.visibilityOfElementLocated(DETAILS_TITLE));
    }

    public int getDisplayedTotal() {
        String text = getDetailsSection().findElement(By.cssSelector(".ac-details-title-group p")).getText();
        String count = text.replaceAll("[^0-9]", "");
        if (count.isEmpty()) {
            throw new AssertionError("Investigation Details total is missing: " + text);
        }
        return Integer.parseInt(count);
    }

    public Map<String, String> getListRows() {
        wait.until(ExpectedConditions.visibilityOfElementLocated(
            By.cssSelector("table.ac-table")));
        Map<String, String> rowsById = new LinkedHashMap<>();
        for (WebElement row : getDetailsSection().findElements(LIST_ROWS)) {
            String idText = row.findElement(By.cssSelector(".ac-inv-id")).getText().trim();
            String id = idText.split("\\s*/\\s*", 2)[0].trim();
            String title = row.findElement(By.cssSelector(".ac-inv-title")).getText().trim();
            rowsById.put(id, title);
        }
        return rowsById;
    }

    public String openFirstInvestigationPreview() {
        wait.until(ExpectedConditions.visibilityOfElementLocated(By.cssSelector("table.ac-table")));
        WebElement firstRow = getDetailsSection().findElements(LIST_ROWS).stream()
                .filter(WebElement::isDisplayed)
                .findFirst()
                .orElseThrow(() -> new AssertionError("No investigation row is available to preview"));
        String idText = firstRow.findElement(By.cssSelector(".ac-inv-id")).getText().trim();
        String investigationId = idText.split("\\s*/\\s*", 2)[0].trim();
        firstRow.click();
        wait.until(ExpectedConditions.visibilityOfElementLocated(PREVIEW_PANEL));
        return investigationId;
    }

    public List<String> getCardIds() {
        return getDetailsSection().findElements(By.cssSelector(".ac-pending-grid .ac-pending-card-id"))
                .stream()
                .map(element -> element.getText().trim())
                .toList();
    }

    public List<String> getBackendFilterOptions(String optionName, Map<String, Object> summary) {
        Map<String, Object> filterOptions = asMap(summary.get("filter_options"));
        Object values = filterOptions.get(optionName);
        if (!(values instanceof List<?> options)) {
            throw new AssertionError("Backend did not return filter options for " + optionName);
        }
        return options.stream().map(String::valueOf).toList();
    }

    public List<String> getRenderedFilterValues(String defaultLabel) {
        Select filter = new Select(wait.until(ExpectedConditions.visibilityOfElementLocated(filterLocator(defaultLabel))));
        List<String> values = new ArrayList<>();
        for (WebElement option : filter.getOptions()) {
            String value = option.getAttribute("value");
            if (value != null && !value.isBlank()) {
                values.add(value);
            }
        }
        return values;
    }

    public void selectFilterAndWait(String defaultLabel, String queryName, String value) {
        By locator = filterLocator(defaultLabel);
        new Select(wait.until(ExpectedConditions.elementToBeClickable(locator))).selectByValue(value);
        wait.until(currentDriver -> Objects.equals(getLatestQueryParameter(queryName), value));
        waitForDataRefresh();
    }

    public void clearFilterAndWait(String defaultLabel, String queryName) {
        By locator = filterLocator(defaultLabel);
        new Select(wait.until(ExpectedConditions.elementToBeClickable(locator))).selectByValue("");
        wait.until(currentDriver -> getLatestQueryParameter(queryName) == null);
        waitForDataRefresh();
    }

    public Map<String, Object> fetchCurrentBackendSummary() {
        String script = "const done = arguments[arguments.length - 1];"
                + "const urls = performance.getEntriesByType('resource').map(entry => entry.name)"
                + ".filter(url => url.includes('/action-center/summary'));"
                + "const url = urls[urls.length - 1];"
                + "if (!url) { done({status: 0, error: 'No summary request found'}); return; }"
                + "const token = localStorage.getItem('auth_token');"
                + "fetch(url, {headers: token ? {Authorization: 'Bearer ' + token} : {}})"
                + ".then(async response => done({status: response.status, payload: await response.json()}))"
                + ".catch(error => done({status: 0, error: String(error)}));";
        Object result = ((JavascriptExecutor) driver).executeAsyncScript(script);
        Map<String, Object> response = asMap(result);
        Number status = (Number) response.get("status");
        if (status == null || status.intValue() != 200) {
            throw new AssertionError("Could not fetch dashboard summary from backend: " + response.get("error"));
        }
        return asMap(response.get("payload"));
    }

    public List<Map<String, Object>> getBackendInvestigations(Map<String, Object> summary) {
        Object value = summary.get("investigations");
        if (!(value instanceof List<?> rows)) {
            throw new AssertionError("Backend summary did not include an investigations list");
        }
        List<Map<String, Object>> investigations = new ArrayList<>();
        for (Object row : rows) {
            investigations.add(asMap(row));
        }
        return investigations;
    }

    public void searchFor(String text) {
        WebElement search = wait.until(ExpectedConditions.visibilityOfElementLocated(
                By.cssSelector("input.ac-search-input")));
        search.clear();
        search.sendKeys(text);
    }

        public void clearSearch(int expectedRowCount) {
        WebElement search = wait.until(ExpectedConditions.visibilityOfElementLocated(
                By.cssSelector("input.ac-search-input")));
        ((JavascriptExecutor) driver).executeScript(
            "const input = arguments[0];"
                + "const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
                + "setter.call(input, '');"
                + "input.dispatchEvent(new Event('input', { bubbles: true }));"
                + "input.dispatchEvent(new Event('change', { bubbles: true }));",
            search);
        wait.until(currentDriver -> search.getAttribute("value").isBlank()
            && getListRows().size() == Math.min(expectedRowCount, 10));
    }

    public void waitForSearchResult(String expectedId) {
        wait.until(currentDriver -> {
            Map<String, String> rows = getListRows();
            return rows.size() == 1 && rows.containsKey(expectedId);
        });
    }

    public String getStartDateFrom() {
        return wait.until(ExpectedConditions.visibilityOfElementLocated(START_DATE)).getAttribute("value");
    }

    public void showAllDatesAndWait() {
        wait.until(ExpectedConditions.elementToBeClickable(SHOW_ALL_DATES)).click();
        wait.until(currentDriver -> getLatestQueryParameter("start_date_from") == null);
        waitForDataRefresh();
    }

    public void switchToCardView() {
        wait.until(ExpectedConditions.elementToBeClickable(CARD_VIEW)).click();
        wait.until(currentDriver -> !getCardIds().isEmpty());
    }

    public void switchToListView() {
        wait.until(ExpectedConditions.elementToBeClickable(LIST_VIEW)).click();
        wait.until(ExpectedConditions.visibilityOfElementLocated(DETAILS_TITLE));
    }

    public void groupCardsTogether() {
        WebElement allGroupButton = getDetailsSection().findElement(By.xpath(".//button[normalize-space()='All']"));
        allGroupButton.click();
    }

    private By filterLocator(String defaultLabel) {
        return By.xpath("//div[contains(@class,'ac-filters')]//select[option[1][normalize-space()='"
                + defaultLabel + "']]");
    }

    public String getLatestQueryParameter(String parameterName) {
        String script = "const urls = performance.getEntriesByType('resource').map(entry => entry.name)"
                + ".filter(url => url.includes('/action-center/summary'));"
                + "return urls.length ? new URL(urls[urls.length - 1]).searchParams.get(arguments[0]) : null;";
        return (String) ((JavascriptExecutor) driver).executeScript(script, parameterName);
    }

    private void waitForDataRefresh() {
        wait.until(currentDriver -> "1".equals(
                currentDriver.findElement(By.cssSelector(".ac-page")).getCssValue("opacity")));
    }

    private WebElement getDetailsSection() {
        return driver.findElement(DETAILS_SECTION);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> asMap(Object value) {
        if (!(value instanceof Map<?, ?>)) {
            throw new AssertionError("Expected a JSON object from the dashboard backend");
        }
        return (Map<String, Object>) value;
    }
}
