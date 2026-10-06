package com.investigationai.qa.modal.feedback;

import java.util.List;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;

import com.investigationai.qa.config.ConfigReader;
import com.investigationai.qa.modal.FileUpload;
import com.investigationai.qa.modal.rating.RatingModal;
import com.investigationai.qa.utils.Reusable;
import com.investigationai.qa.utils.ScreenshotIsAvailable;
import com.investigationai.qa.utils.TokenUtil;
import com.investigationai.qa.utils.WaitUtils;

public class BugIssueModal {

    private final WebDriver driver;
    private final Reusable reusable;
    private final RatingModal ratingModal;
    private final FileUpload fileUpload;

    @FindBy(xpath = "//input[@type='file']")
    private WebElement screenshot;

    @FindBy(xpath = "//button[contains(.,'Submit feedback')]")
    private WebElement submitFeedbackBtn;

    @FindBy(xpath = "//textarea[@id='fb-steps']")
    private WebElement stepsToReproduceTextArea;

    @FindBy(xpath = "//input[@id='fb-users']")
    private WebElement noOfUserAffectedText;

    public BugIssueModal(WebDriver driver) {
        this.driver = driver;
        PageFactory.initElements(driver, this);
        this.reusable = new Reusable(driver);
        this.ratingModal = new RatingModal(driver);
        this.fileUpload = new FileUpload(screenshot);
    }

    public void enterNumberOfUsersAffected(int numbers) {
        WaitUtils.visible(driver, noOfUserAffectedText);
        noOfUserAffectedText.click();
        noOfUserAffectedText.clear();
        noOfUserAffectedText.sendKeys(String.valueOf(numbers));
    }

    public String selectImpact(String impact) {
        List<WebElement> dropdowns = driver.findElements(By.xpath("//span[@data-slot='select-value']/parent::button"));
        if (dropdowns.size() < 1) {
            throw new RuntimeException("Impact dropdown not found.");
        }
        WebElement impactDropdown = dropdowns.get(0);
        WaitUtils.visible(driver, impactDropdown);
        impactDropdown.click();
        List<WebElement> options = driver.findElements(By.xpath("//div[@role='option']"));
        for (WebElement option : options) {
            WaitUtils.visible(driver, option);
            String optionText = option.getText().trim();
            System.out.println("Impact option found: " + optionText);
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

    public String urgencyDropdown(String urgency) {
        List<WebElement> dropdowns = driver.findElements(By.xpath("//span[@data-slot='select-value']/parent::button"));
        if (dropdowns.size() < 1) {
            throw new RuntimeException("Urgency dropdown not found.");
        }
        WebElement urgencyDropdown = dropdowns.get(1);
        WaitUtils.visible(driver, urgencyDropdown);
        urgencyDropdown.click();
        List<WebElement> options = driver.findElements(By.xpath("//div[@role='option']"));
        for (WebElement option : options) {
            WaitUtils.visible(driver, option);
            String optionText = option.getText().trim();
            System.out.println("Urgency option found: " + optionText);
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

    public BugIssueModal uploadScreenshot(String filePath) {
        fileUpload.upload(filePath);
        return this;
    }

    public void selectRating(int rating) {
        ratingModal.selectRating(rating);
    }

    public void submitFeedback() {
        WaitUtils.visible(driver, stepsToReproduceTextArea);
        String authToken = TokenUtil.getAccessToken(driver);
        if (authToken == null || authToken.isBlank()) {
            throw new RuntimeException("Access Token not found. User may not be logged in.");
        }

        reusable.enterBugDetails();
        selectRating(4);

        String selectedFrequency = reusable.selectUsageFrequency("Daily");
        System.out.println("Selected frequency: " + selectedFrequency);

        WaitUtils.visible(driver, stepsToReproduceTextArea);
        stepsToReproduceTextArea.sendKeys(ConfigReader.get("STEPS_TO_REPRODUCE"));

        reusable.selectRecommendation(true);

        enterNumberOfUsersAffected(4);

        selectImpact("Medium");
        urgencyDropdown("Immediate");

        ScreenshotIsAvailable.chooseAndUploadScreenshot("Bug", fileUpload);

        WaitUtils.visible(driver, submitFeedbackBtn);
        submitFeedbackBtn.click();

        System.out.println("Bug feedback submitted successfully.");
    }
}
