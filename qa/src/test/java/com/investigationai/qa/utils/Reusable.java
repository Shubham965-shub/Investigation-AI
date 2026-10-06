package com.investigationai.qa.utils;

import java.util.List;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;

import com.investigationai.qa.config.ConfigReader;
import com.investigationai.qa.driver.DriverFactory;

public class Reusable {

    @FindBy(id = "fb-title")
    private WebElement summary;

    @FindBy(id = "fb-details")
    private WebElement description;

    @FindBy(xpath = "//textarea[@id='fb-expected']")
    private WebElement expectedResult;

    @FindBy(xpath = "//textarea[@id='fb-actual']")
    private WebElement actualResult;

    @FindBy(xpath = "//label[contains(.,'Usage frequency')]/following-sibling::button")
    private WebElement usageFrequencyDropdown;

    @FindBy(xpath = "//button[normalize-space()='Yes']")
    private WebElement recommendYes;

    @FindBy(xpath = "//button[normalize-space()='No']")
    private WebElement recommendNo;

    private final String summaryText = ConfigReader.get("SUMMARY");
    private final String descText = ConfigReader.get("DESCRIPTION");
    private final String expectedResultText = ConfigReader.get("EXPECTED_RESULT");
    private final String actualResultText = ConfigReader.get("ACTUAL_RESULT");

    public Reusable(WebDriver driver) {
        PageFactory.initElements(driver, this);
    }

    public void enterSummary() {
        WebDriver driver = DriverFactory.getDriver();
        WaitUtils.visible(driver, summary);
        summary.clear();
        summary.sendKeys(summaryText);
    }

    public void enterDescription() {
        WebDriver driver = DriverFactory.getDriver();
        WaitUtils.visible(driver, description);
        description.clear();
        description.sendKeys(descText);
    }

    public void enterExpectedResult() {
        WebDriver driver = DriverFactory.getDriver();
        WaitUtils.visible(driver, expectedResult);
        expectedResult.clear();
        expectedResult.sendKeys(expectedResultText);
    }

    public void enterActualResult() {
        WebDriver driver = DriverFactory.getDriver();
        WaitUtils.visible(driver, actualResult);
        actualResult.clear();
        actualResult.sendKeys(actualResultText);
    }

    public void enterEnhancementText() {
        enterSummary();
        enterDescription();
    }

    public void enterFeedbackDetails() {
        enterSummary();
        enterDescription();
    }

    public void enterBugDetails() {
        enterSummary();
        enterDescription();
        enterExpectedResult();
        enterActualResult();
    }

    public String selectUsageFrequency(String frequency) {
        WebDriver driver = DriverFactory.getDriver();
        WaitUtils.visible(driver, usageFrequencyDropdown);
        usageFrequencyDropdown.click();
        List<WebElement> options = driver.findElements(By.xpath("//div[@role='option']"));
        for (WebElement option : options) {
            WaitUtils.visible(driver, option);
            String optionText = option.getText().trim();
            System.out.println("Frequency option found: [" + optionText + "]");
            if (optionText.equalsIgnoreCase(frequency)) {
                option.click();
                WaitUtils.visible(driver, usageFrequencyDropdown);
                String selected = usageFrequencyDropdown.getText().trim();
                System.out.println("Selected frequency: " + selected);
                return selected;
            }
        }
        throw new RuntimeException("Usage frequency option not found: " + frequency);
    }

    public String selectRecommendation(boolean recommend) {
        WebDriver driver = DriverFactory.getDriver();
        if (recommend) {
            WaitUtils.visible(driver, recommendYes);
            recommendYes.click();
            System.out.println("Recommended button clicked: Yes");
            return "Yes";
        } else {
            WaitUtils.visible(driver, recommendNo);
            recommendNo.click();
            System.out.println("Recommended button clicked: No");
            return "No";
        }
    }

    public String selectImpact(String impact) {
        WebDriver driver = DriverFactory.getDriver();
        WebElement impactDropdown = driver
                .findElement(By.xpath("//label[contains(.,'Impact')]/following-sibling::button"));
        WaitUtils.visible(driver, impactDropdown);
        impactDropdown.click();
        List<WebElement> options = driver.findElements(By.xpath("//div[@role='option']"));
        for (WebElement option : options) {
            WaitUtils.visible(driver, option);
            String optionText = option.getText().trim();
            System.out.println("Impact option found: [" + optionText + "]");
            if (optionText.equalsIgnoreCase(impact)) {
                option.click();
                WaitUtils.visible(driver, impactDropdown);
                String selectedImpact = impactDropdown.getText().trim();
                System.out.println("Selected Impact: " + selectedImpact);
                return selectedImpact;
            }
        }
        throw new RuntimeException("Impact option not found: " + impact);
    }

    public String selectUrgency(String urgency) {
        WebDriver driver = DriverFactory.getDriver();
        WebElement urgencyDropdown = driver
                .findElement(By.xpath("//label[contains(.,'Urgency')]/following-sibling::button"));
        WaitUtils.visible(driver, urgencyDropdown);
        urgencyDropdown.click();
        List<WebElement> options = driver.findElements(By.xpath("//div[@role='option']"));
        for (WebElement option : options) {
            WaitUtils.visible(driver, option);
            String optionText = option.getText().trim();
            System.out.println("Urgency option found: [" + optionText + "]");
            if (optionText.equalsIgnoreCase(urgency)) {
                option.click();
                WaitUtils.visible(driver, urgencyDropdown);
                String selectedUrgency = urgencyDropdown.getText().trim();
                System.out.println("Selected Urgency: " + selectedUrgency);
                return selectedUrgency;
            }
        }
        throw new RuntimeException("Urgency option not found: " + urgency);
    }

}
