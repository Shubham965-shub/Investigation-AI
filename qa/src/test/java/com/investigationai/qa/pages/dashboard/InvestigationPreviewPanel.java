package com.investigationai.qa.pages.dashboard;

import java.time.Duration;
import java.util.List;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

public class InvestigationPreviewPanel {

    private static final By PANEL = By.cssSelector("div[role='dialog']");
    private static final List<String> WORKFLOW_STEPS = List.of(
            "Problem Statement Generation",
            "Evidence Collection",
            "Interview Questionnaire",
            "RCI Plan Creation",
            "Task Critique",
            "RC, Impact & CAPA Critique");

    private final WebDriver driver;
    private final WebDriverWait wait;

    public InvestigationPreviewPanel(WebDriver driver) {
        this.driver = driver;
        wait = new WebDriverWait(driver, Duration.ofSeconds(15));
        wait.until(ExpectedConditions.attributeToBe(PANEL, "aria-hidden", "false"));
    }

    public String getInvestigationId() {
        return getDialog().findElements(By.cssSelector("span[style*='monospace']")).get(0).getText().trim();
    }

    public String getEventType() {
        return getDialog().findElements(By.cssSelector("span[style*='monospace']")).get(1).getText().trim();
    }

    public String getTitle() {
        return getDialog().findElements(By.tagName("p")).get(0).getText().trim();
    }

    public int getProgressPercent() {
        String value = getDialog().findElement(By.xpath(
                ".//p[normalize-space()='Overall Progress']/following-sibling::div[1]/span[1]")).getText().trim();
        return Integer.parseInt(value.replace("%", ""));
    }

    public String getProgressStepsText() {
        return getDialog().findElement(By.xpath(
                ".//p[normalize-space()='Overall Progress']/following-sibling::div[1]/span[2]")).getText().trim();
    }

    public String getDueDate() {
        return getSummaryValue("Due Date");
    }

    public String getLastUpdated() {
        return getSummaryValue("Last Updated");
    }

    public String getInvestigationTeamText() {
        return getDialog().findElement(By.xpath(
            ".//p[normalize-space()='Investigation Team']/ancestor::div[1]/following-sibling::div[1]"))
                .getText().trim();
    }

    public List<String> getWorkflowStepLabels() {
        return getDialog().findElements(By.xpath(
                ".//p[normalize-space()='Problem Statement Generation' or "
                        + "normalize-space()='Evidence Collection' or "
                        + "normalize-space()='Interview Questionnaire' or "
                        + "normalize-space()='RCI Plan Creation' or "
                        + "normalize-space()='Task Critique' or "
                        + "normalize-space()='RC, Impact & CAPA Critique']"))
                .stream()
                .map(element -> element.getText().trim())
                .toList();
    }

    public String getWorkflowStepStatus(String label) {
        WebElement stepLabel = getDialog().findElement(By.xpath(".//p[normalize-space()='" + label + "']"));
        WebElement stepCard = stepLabel.findElement(By.xpath("ancestor::div[@role='button'][1]"));
        return stepCard.findElement(By.xpath(
                ".//span[normalize-space()='Completed' or normalize-space()='In Progress' or normalize-space()='Not Started']"))
                .getText().trim();
    }

    public void close() {
        getDialog().findElement(By.cssSelector("button[aria-label='Close panel']")).click();
        wait.until(ExpectedConditions.attributeToBe(PANEL, "aria-hidden", "true"));
    }

    private WebElement getDialog() {
        wait.until(ExpectedConditions.attributeToBe(PANEL, "aria-hidden", "false"));
        return driver.findElement(PANEL);
    }

    private String getSummaryValue(String label) {
        WebElement labelElement = getDialog().findElement(By.xpath(".//p[normalize-space()='" + label + "']"));
        WebElement valueElement = labelElement.findElement(By.xpath("following-sibling::p[1]"));
        wait.until(ExpectedConditions.visibilityOf(valueElement));
        return valueElement.getAttribute("textContent").trim();
    }

    public static List<String> expectedWorkflowSteps() {
        return WORKFLOW_STEPS;
    }
}
