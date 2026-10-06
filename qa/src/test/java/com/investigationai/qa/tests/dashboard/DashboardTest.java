package com.investigationai.qa.tests.dashboard;

import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import org.openqa.selenium.WebDriver;
import org.testng.Assert;
import org.testng.annotations.Test;

import com.investigationai.qa.base.BaseTest;
import com.investigationai.qa.config.ConfigReader;
import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.modal.account.ChangePasswordModal;
import com.investigationai.qa.pages.dashboard.InvestigationDetailsPage;
import com.investigationai.qa.pages.dashboard.InvestigationPreviewPanel;

public class DashboardTest extends BaseTest {

    private void loginConfiguredUser() {
        loginPage.login(ConfigReader.get("username"), ConfigReader.get("password"));
        Assert.assertTrue(dashboardPage.isDashboardPageDisplayed(), "Dashboard was not displayed after login");
    }

    @Test(groups = "smoke", description = "A valid user can sign in and reach the dashboard")
    public void validUserCanReachDashboard() {
        loginConfiguredUser();
    }

    @Test(groups = "sanity", description = "Dashboard investigation and L1-L5 counts match backend summary")
    public void dashboardKpiAndStatusCountsMatchBackend() {
        loginConfiguredUser();
        Map<String, Object> summary = new InvestigationDetailsPage(DriverFactory.getDriver())
                .fetchCurrentBackendSummary();

        Map<String, Integer> dashboardKpis = dashboardPage.getKpiCounts();
        Assert.assertEquals(dashboardKpis.get("OPEN INVESTIGATIONS"),
                ((Number) summary.get("total_investigations")).intValue(),
                "Open Investigations count does not match backend summary");

        Map<String, Integer> expectedEventCounts = new LinkedHashMap<>();
        for (Map<String, Object> eventType : asMapList(summary.get("event_type_counts"), "event_type_counts")) {
            String label = String.valueOf(eventType.get("label")).toUpperCase(Locale.ROOT);
            expectedEventCounts.put(label, ((Number) eventType.get("count")).intValue());
        }
        int totalFromEventTypes = 0;
        for (String eventType : List.of("DEVIATION", "OOS", "OOT", "MARKET COMPLAINT")) {
            Assert.assertTrue(dashboardKpis.containsKey(eventType), "Missing dashboard KPI for " + eventType);
            Assert.assertTrue(expectedEventCounts.containsKey(eventType),
                "Backend summary is missing event type " + eventType);
            Assert.assertEquals(dashboardKpis.get(eventType), expectedEventCounts.get(eventType),
                    eventType + " KPI does not match backend summary");
            totalFromEventTypes += expectedEventCounts.get(eventType);
        }
        Assert.assertEquals(totalFromEventTypes, ((Number) summary.get("total_investigations")).intValue(),
            "Open Investigations must equal Deviation + OOS + OOT + Market Complaint");

        Map<String, Integer> expectedEscalationCounts = new LinkedHashMap<>();
        for (Map<String, Object> statusCard : asMapList(summary.get("status_cards"), "status_cards")) {
            String key = String.valueOf(statusCard.get("key")).toUpperCase(Locale.ROOT);
            if (List.of("L1", "L2", "L3", "L4", "L5").contains(key)) {
                expectedEscalationCounts.put(key, ((Number) statusCard.get("count")).intValue());
            }
        }
        Assert.assertEquals(expectedEscalationCounts.size(), 5, "Backend summary must include status counts L1-L5");
        Assert.assertEquals(dashboardPage.getEscalationCounts(), expectedEscalationCounts,
                "Dashboard L1-L5 counts do not match backend summary");

        List<Map<String, Object>> investigations = asMapList(summary.get("investigations"), "investigations");
        Map<String, Integer> escalationCountsFromRows = new LinkedHashMap<>();
        for (String level : List.of("L1", "L2", "L3", "L4", "L5")) {
            escalationCountsFromRows.put(level, 0);
        }

        Map<String, Integer> trackWiseBuckets = new LinkedHashMap<>();
        for (String bucket : List.of("on_track", "delay", "overdue", "unassigned")) {
            trackWiseBuckets.put(bucket, 0);
        }

        for (Map<String, Object> investigation : investigations) {
            String level = String.valueOf(investigation.get("escalation_level")).toUpperCase(Locale.ROOT);
            if (escalationCountsFromRows.containsKey(level)) {
            escalationCountsFromRows.compute(level, (key, count) -> count + 1);
            }

            String bucket = String.valueOf(investigation.get("bucket"));
            Assert.assertTrue(trackWiseBuckets.containsKey(bucket),
                "Backend returned an unsupported TrackWise bucket: " + bucket);
            trackWiseBuckets.compute(bucket, (key, count) -> count + 1);
        }

        Assert.assertEquals(escalationCountsFromRows, expectedEscalationCounts,
            "Backend L1-L5 cards must count investigations by escalation_level");
        Assert.assertEquals(trackWiseBuckets.values().stream().mapToInt(Integer::intValue).sum(),
            investigations.size(), "TrackWise buckets must classify every returned investigation once");
    }

    @Test(groups = "sanity", description = "Dashboard header and account selection work")
    public void dashboardAccountSelectionWorks() {
        loginConfiguredUser();
        Assert.assertTrue(dashboardPage.isStridesLogoDisplayed(), "Strides logo is not displayed");
        Assert.assertTrue(dashboardPage.isAthenaLogoDisplayed(), "Athena logo is not displayed");
        Assert.assertTrue(dashboardPage.isOpenInvestigationsCardDisplayed(),
                "Open Investigations KPI is not displayed");
        Assert.assertTrue(dashboardPage.areEventTypeCardsDisplayed(),
                "All event-type KPI cards are not displayed");
        Assert.assertTrue(dashboardPage.isAccountMenuDisplayed(), "Account menu is not displayed");

        List<String> accounts = dashboardPage.getAvailableAccounts();
        String myAccount = accounts.stream()
            .filter(account -> account.contains("My account"))
            .findFirst()
            .orElseThrow(() -> new AssertionError("My account option is not available"));
        String investigatorAccount = accounts.stream()
            .filter(account -> !account.equals(myAccount))
            .findFirst()
            .orElseThrow(() -> new AssertionError("No investigator account option is available"));

        dashboardPage.selectAccount(investigatorAccount);
        Assert.assertTrue(dashboardPage.getDashboardTitle().startsWith("Action Center - Investigator View"),
            "Selecting an investigator account did not switch dashboard view");
        dashboardPage.selectAccount(myAccount);
        Assert.assertTrue(dashboardPage.isDashboardPageDisplayed(), "Selecting My account did not restore the dashboard");

        dashboardPage.logout();
        Assert.assertTrue(loginPage.isLoginFormDisplayed(), "Logout did not return to the login form");
    }

        @Test(groups = "sanity", description = "Investigation preview details and workflow stages match backend data")
        public void investigationPreviewMatchesBackendData() {
        loginConfiguredUser();
        WebDriver driver = DriverFactory.getDriver();
        InvestigationDetailsPage details = new InvestigationDetailsPage(driver);
        Map<String, Object> summary = details.fetchCurrentBackendSummary();
        List<Map<String, Object>> investigations = details.getBackendInvestigations(summary);
        Assert.assertFalse(investigations.isEmpty(), "Backend returned no investigation to preview");

        String openedId = details.openFirstInvestigationPreview();
        Map<String, Object> backendInvestigation = investigations.stream()
            .filter(investigation -> openedId.equals(String.valueOf(investigation.get("id"))))
            .findFirst()
            .orElseThrow(() -> new AssertionError("Opened investigation is absent from backend summary: " + openedId));

        InvestigationPreviewPanel preview = new InvestigationPreviewPanel(driver);
        Assert.assertEquals(preview.getInvestigationId(), openedId, "Preview shows the wrong investigation ID");
        Assert.assertEquals(normalizeWhitespace(preview.getTitle()),
            normalizeWhitespace(String.valueOf(backendInvestigation.get("title"))),
            "Preview title does not match backend data");
        Assert.assertEquals(preview.getEventType(), String.valueOf(backendInvestigation.get("event_type")),
            "Preview event type does not match backend data");

        int stage = ((Number) backendInvestigation.get("stage")).intValue();
        int totalStages = ((Number) backendInvestigation.get("total_stages")).intValue();
        int expectedPercent = totalStages == 0 ? 0 : (int) Math.floor((100.0 * stage / totalStages) + 0.5);
        Assert.assertEquals(preview.getProgressPercent(), expectedPercent,
            "Preview overall progress percentage does not match backend stage data");
        Assert.assertEquals(preview.getProgressStepsText(),
            stage + " of " + totalStages + " steps complete",
            "Preview progress step count does not match backend data");

        Assert.assertEquals(preview.getDueDate(), backendDisplayValue(backendInvestigation.get("due_date")),
            "Preview due date does not match backend data");
        String investigator = backendInvestigation.get("investigator") == null
            ? "Unassigned"
            : String.valueOf(backendInvestigation.get("investigator"));
        Assert.assertTrue(preview.getInvestigationTeamText().contains(investigator),
            "Preview investigation team does not match backend investigator");

        List<String> expectedSteps = InvestigationPreviewPanel.expectedWorkflowSteps();
        List<String> visibleSteps = preview.getWorkflowStepLabels();
        Assert.assertTrue(visibleSteps.containsAll(expectedSteps),
            "Preview is missing one or more configured investigation workflow stages");
        for (int index = 0; index < expectedSteps.size(); index++) {
            String expectedStatus = index < stage ? "Completed" : index == stage ? "In Progress" : "Not Started";
            if (index < stage || index == stage) {
            Assert.assertEquals(preview.getWorkflowStepStatus(expectedSteps.get(index)), expectedStatus,
                "Unexpected workflow status for " + expectedSteps.get(index));
            }
        }
        Assert.assertEquals(preview.getLastUpdated(), backendDisplayValue(backendInvestigation.get("updated_at")),
            "Preview last-updated value does not match backend data");
        preview.close();
        }

        @Test(groups = "sanity", description = "Investigation Details data, search, filters, date range, and views match the backend")
        public void investigationDetailsMatchBackendAcrossFiltersAndViews() {
        loginConfiguredUser();
        WebDriver driver = DriverFactory.getDriver();
        InvestigationDetailsPage details = new InvestigationDetailsPage(driver);
        Map<String, Object> baselineSummary = details.fetchCurrentBackendSummary();
        List<Map<String, Object>> baselineInvestigations = details.getBackendInvestigations(baselineSummary);

        Assert.assertTrue(baselineInvestigations.size() > 0, "Backend returned no open investigations to validate");
        Assert.assertEquals(details.getDisplayedTotal(), ((Number) baselineSummary.get("total_investigations")).intValue(),
            "Investigation Details total does not match the backend summary");

        Map<String, String> firstPage = details.getListRows();
        Assert.assertTrue(firstPage.size() > 0, "Investigation Details list is empty");
        Assert.assertTrue(firstPage.size() <= 10, "List View should paginate to at most 10 investigations");
        assertVisibleRowsMatchBackend(firstPage, baselineInvestigations);

        String searchId = firstPage.keySet().iterator().next();
        details.searchFor(searchId);
        details.waitForSearchResult(searchId);
        Map<String, String> searchedRows = details.getListRows();
        Assert.assertEquals(searchedRows.size(), 1, "Searching by investigation ID should return one row");
        Assert.assertEquals(searchedRows.get(searchId), firstPage.get(searchId),
            "Search result title does not match the backend investigation");
        details.clearSearch(baselineInvestigations.size());

        verifyBackendFilter(details, baselineSummary, baselineInvestigations,
            "All Sites", "sites", "site");
        verifyBackendFilter(details, baselineSummary, baselineInvestigations,
            "Dept", "departments", "department");
        verifyBackendFilter(details, baselineSummary, baselineInvestigations,
            "Product", "products", "product");

        String defaultStartDate = details.getStartDateFrom();
        Assert.assertFalse(defaultStartDate.isBlank(), "Admin/SIT dashboard should show the default start-date filter");
        details.showAllDatesAndWait();
        Assert.assertTrue(details.getStartDateFrom().isBlank(), "Show all dates did not clear the start-date filter");
        Assert.assertNull(details.getLatestQueryParameter("start_date_from"),
            "Backend request should omit start_date_from after Show all dates");
        Map<String, Object> allDatesSummary = details.fetchCurrentBackendSummary();
        List<Map<String, Object>> allDatesInvestigations = details.getBackendInvestigations(allDatesSummary);

        details.switchToCardView();
        details.groupCardsTogether();
        Set<String> cardIds = new HashSet<>(details.getCardIds());
        Set<String> backendIds = new HashSet<>();
        for (Map<String, Object> investigation : allDatesInvestigations) {
            backendIds.add(String.valueOf(investigation.get("id")));
        }
        Assert.assertEquals(cardIds, backendIds, "Card View IDs do not match all investigations returned by the backend");

        details.switchToListView();
        Assert.assertTrue(details.getListRows().size() <= 10, "List View pagination limit was not restored");
        }

        private void verifyBackendFilter(
            InvestigationDetailsPage details,
            Map<String, Object> baselineSummary,
            List<Map<String, Object>> baselineInvestigations,
            String defaultLabel,
            String backendOptionKey,
            String queryParameter) {
        List<String> backendOptions = details.getBackendFilterOptions(backendOptionKey, baselineSummary);
        List<String> renderedOptions = details.getRenderedFilterValues(defaultLabel);
        Assert.assertEquals(new HashSet<>(renderedOptions), new HashSet<>(backendOptions),
            defaultLabel + " options do not match backend filter options");
        if (backendOptions.isEmpty()) {
            return;
        }

        String selectedValue = backendOptions.get(0);
        details.selectFilterAndWait(defaultLabel, queryParameter, selectedValue);
        Map<String, Object> filteredSummary = details.fetchCurrentBackendSummary();
        List<Map<String, Object>> filteredInvestigations = details.getBackendInvestigations(filteredSummary);
        Assert.assertTrue(filteredInvestigations.stream()
            .allMatch(investigation -> selectedValue.equals(investigation.get(queryParameter))),
            defaultLabel + " backend results contain rows outside the selected filter");
        assertVisibleRowsMatchBackend(details.getListRows(), filteredInvestigations);
        details.clearFilterAndWait(defaultLabel, queryParameter);
        Assert.assertEquals(details.getListRows().size() > 0, !baselineInvestigations.isEmpty(),
            defaultLabel + " clear did not restore visible investigation data");
        }

        private void assertVisibleRowsMatchBackend(
            Map<String, String> visibleRows,
            List<Map<String, Object>> backendInvestigations) {
        Map<String, String> backendTitlesById = new java.util.HashMap<>();
        for (Map<String, Object> investigation : backendInvestigations) {
            backendTitlesById.put(String.valueOf(investigation.get("id")),
                String.valueOf(investigation.get("title")));
        }
        for (Map.Entry<String, String> visibleRow : visibleRows.entrySet()) {
            Assert.assertEquals(normalizeWhitespace(visibleRow.getValue()),
                    normalizeWhitespace(backendTitlesById.get(visibleRow.getKey())),
                "Visible investigation does not match backend data for ID " + visibleRow.getKey());
        }
        }

    private List<Map<String, Object>> asMapList(Object value, String fieldName) {
        Assert.assertTrue(value instanceof List<?>, "Backend summary is missing " + fieldName);
        List<Map<String, Object>> result = new java.util.ArrayList<>();
        for (Object item : (List<?>) value) {
            Assert.assertTrue(item instanceof Map<?, ?>, "Backend summary contains invalid " + fieldName + " data");
            @SuppressWarnings("unchecked")
            Map<String, Object> map = (Map<String, Object>) item;
            result.add(map);
        }
        return result;
    }

    private String normalizeWhitespace(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").trim();
    }

    private String backendDisplayValue(Object value) {
        return value == null || String.valueOf(value).isBlank() ? "—" : String.valueOf(value);
    }

    @Test(groups = "sanity", description = "Account menu changes and restores the signed-in user's password")
    public void accountMenuPasswordCanBeChanged() {
        loginConfiguredUser();
        ChangePasswordModal changePasswordModal = dashboardPage.openChangePasswordModal();
        Assert.assertTrue(changePasswordModal.isDisplayed(), "Change Password modal is not displayed");
        String username = ConfigReader.get("username");
        String originalPassword = ConfigReader.get("password");
        String changedPassword = originalPassword + "QaChanged1";
        changePasswordModal.changePassword(originalPassword, changedPassword);
        dashboardPage.logout();

        loginPage.login(username, changedPassword);
        Assert.assertTrue(dashboardPage.isDashboardPageDisplayed(),
            "Login failed with the changed password");
        ChangePasswordModal restorePasswordModal = dashboardPage.openChangePasswordModal();
        restorePasswordModal.changePassword(changedPassword, originalPassword);

        dashboardPage.logout();
        Assert.assertTrue(loginPage.isLoginFormDisplayed(), "Logout did not return to the login form");
    }
}
