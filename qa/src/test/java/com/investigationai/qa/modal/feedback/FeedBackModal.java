package com.investigationai.qa.modal.feedback;

import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;

import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.modal.FileUpload;
import com.investigationai.qa.modal.rating.RatingModal;
import com.investigationai.qa.utils.Reusable;
import com.investigationai.qa.utils.ScreenshotIsAvailable;
import com.investigationai.qa.utils.TokenUtil;
import com.investigationai.qa.utils.WaitUtils;

public class FeedBackModal {

    @FindBy(xpath = "//h2[contains(text(),'Share feedback')]")
    private WebElement title;

    // Tabs
    @FindBy(xpath = "//*[contains(text(),'Give feedback')]")
    private WebElement giveFeedbackTab;

    @FindBy(xpath = "//*[contains(text(),'Vote on features')]")
    private WebElement voteOnFeatureTab;

    // Common fields
    @FindBy(xpath = "//input[@type='file']")
    private WebElement screenshot;

    @FindBy(xpath = "//button[contains(.,'Submit feedback')]")
    private WebElement submitFeedbackBtn;

    private final Reusable reusable;
    private final RatingModal ratingModal;
    private final FileUpload fileUpload;

    public FeedBackModal(WebDriver driver) {
        PageFactory.initElements(driver, this);

        this.reusable = new Reusable(driver);
        this.ratingModal = new RatingModal(driver);
        this.fileUpload = new FileUpload(screenshot);
    }

    public FeedBackModal uploadScreenshot(String filePath) {
        fileUpload.upload(filePath);
        return this;
    }

    public void selectRating(int rating) {
        ratingModal.selectRating(rating);
    }

    public void submitFeedback() {

        WebDriver driver = DriverFactory.getDriver();
        WaitUtils.visible(driver, giveFeedbackTab);
        String authToken = TokenUtil.getAccessToken(driver);
        if (authToken == null || authToken.isBlank()) {
            throw new RuntimeException("Access Token not found. User may not be logged in.");
        }

        reusable.enterFeedbackDetails();
        selectRating(4);
        String selectedFrequency = reusable.selectUsageFrequency("Weekly");
        System.out.println("Selected frequency: " + selectedFrequency);
        String selectedRecommendation = reusable.selectRecommendation(false);

        System.out.println("Recommended button clicked: "+ selectedRecommendation);
    
        ScreenshotIsAvailable.chooseAndUploadScreenshot("feedback",fileUpload);

        // Submit feedback
        WaitUtils.visible(driver, submitFeedbackBtn);
        submitFeedbackBtn.click();
        System.out.println("Feedback submitted successfully.");
    }

}
