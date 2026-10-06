package com.investigationai.qa.modal.feedback;

import java.util.List;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;

import com.investigationai.qa.modal.FileUpload;
import com.investigationai.qa.modal.rating.RatingModal;
import com.investigationai.qa.utils.Reusable;
import com.investigationai.qa.utils.ScreenshotIsAvailable;
import com.investigationai.qa.utils.TokenUtil;
import com.investigationai.qa.utils.WaitUtils;

public class NewFeatureModal {

    private final WebDriver driver;
    private final Reusable reusable;
    private final RatingModal ratingModal;
    private final FileUpload fileUpload;

    @FindBy(xpath = "//input[@type='file']")
    private WebElement screenshot;

    @FindBy(xpath = "//label[contains(.,'HOD / CXO approval')]/following-sibling::button")
    private WebElement approvalDropdown;

    @FindBy(xpath = "//button[contains(.,'Submit feedback')]")
    private WebElement submitFeedbackBtn;

    public NewFeatureModal(WebDriver driver) {
        this.driver = driver;
        PageFactory.initElements(driver, this);
        this.reusable = new Reusable(driver);
        this.ratingModal = new RatingModal(driver);
        this.fileUpload = new FileUpload(screenshot);
    }

    public void selectRating(int rating) {
        ratingModal.selectRating(rating);
    }

    public String selectApproval(String approval) {
        WaitUtils.visible(driver, approvalDropdown);
        approvalDropdown.click();
        List<WebElement> options = driver.findElements(By.xpath("//div[@role='option']"));
        for (WebElement option : options) {
            WaitUtils.visible(driver, option);
            String optionText = option.getText().trim();
            System.out.println("HOD/CXO Approval option found: " + optionText);
            if (optionText.equalsIgnoreCase(approval)) {
                option.click();
                WaitUtils.visible(driver, approvalDropdown);
                String selected = approvalDropdown.getText().trim();
                System.out.println("Selected HOD/CXO Approval: " + selected);
                return selected;
            }
        }
        throw new RuntimeException("HOD/CXO Approval option not found: " + approval);
    }

    public NewFeatureModal uploadScreenshot(String filePath) {
        fileUpload.upload(filePath);
        return this;
    }

    public void submitFeedback() {
        String authToken = TokenUtil.getAccessToken(driver);
        if (authToken == null || authToken.isBlank()) {
            throw new RuntimeException("Access Token not found. User may not be logged in.");
        }

        reusable.enterFeedbackDetails();

        selectRating(4);

        String selectedFrequency = reusable.selectUsageFrequency("Daily");
        System.out.println("Selected frequency: " + selectedFrequency);

        String selectedRecommendation = reusable.selectRecommendation(true);
        System.out.println("Selected recommendation: " + selectedRecommendation);

        String selectedImpact = reusable.selectImpact("Medium");
        System.out.println("Selected Impact: " + selectedImpact);

        String selectedUrgency = reusable.selectUrgency("Immediate");
        System.out.println("Selected Urgency: " + selectedUrgency);

        String selectedApproval = selectApproval("I have approval");
        System.out.println("Selected HOD/CXO Approval: " + selectedApproval);

        ScreenshotIsAvailable.chooseAndUploadScreenshot("New Feature", fileUpload);

        WaitUtils.visible(driver, submitFeedbackBtn);
        submitFeedbackBtn.click();

        System.out.println("New feature feedback submitted successfully.");
    }
}
