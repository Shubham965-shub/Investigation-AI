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

public class EnhancementModal {

    private final WebDriver driver;
    private final Reusable reusable;
    private final RatingModal ratingModal;
    private final FileUpload fileUpload;

    @FindBy(xpath = "//input[@type='file']")
    private WebElement screenshot;

    @FindBy(xpath = "//input[@id='fb-existing']")
    private WebElement existingFeatureToEnhanceText;

    @FindBy(xpath = "//textarea[@id='fb-benefit']")
    private WebElement additionalBenefit;

    @FindBy(xpath = "//input[@id='fb-needed']")
    private WebElement neededByDate;

    @FindBy(xpath = "//label[contains(.,'HOD approval')]/following-sibling::button")
    private WebElement hodApprovalDropdown;

    public EnhancementModal(WebDriver driver) {
        this.driver = driver;
        PageFactory.initElements(driver, this);
        this.reusable = new Reusable(driver);
        this.ratingModal = new RatingModal(driver);
        this.fileUpload = new FileUpload(screenshot);
    }

    public EnhancementModal uploadScreenshot(String filePath) {
        fileUpload.upload(filePath);
        return this;
    }

    public void selectRating(int rating) {
        ratingModal.selectRating(rating);
    }

    public void enterNeededByDate(String date) {
        WaitUtils.visible(driver, neededByDate);
        neededByDate.click();
        neededByDate.clear();
        neededByDate.sendKeys(date);
    }

    public String selectHodApproval(String approval) {
        WaitUtils.visible(driver, hodApprovalDropdown);
        hodApprovalDropdown.click();
        List<WebElement> options = driver.findElements(By.xpath("//div[@role='option']"));
        for (WebElement option : options) {
            WaitUtils.visible(driver, option);
            String optionText = option.getText().trim();
            System.out.println("HOD Approval option found: " + optionText);
            if (optionText.equalsIgnoreCase(approval)) {
                option.click();
                WaitUtils.visible(driver, hodApprovalDropdown);
                String selected = hodApprovalDropdown.getText().trim();
                System.out.println("Selected HOD Approval: " + selected);
                return selected;
            }
        }
        throw new RuntimeException("HOD Approval option not found: " + approval);
    }

    public void submitFeedback() {
        String authToken = TokenUtil.getAccessToken(driver);
        if (authToken == null || authToken.isBlank()) {
            throw new RuntimeException("Access Token not found. User may not be logged in.");
        }

        WaitUtils.visible(driver, existingFeatureToEnhanceText);
        existingFeatureToEnhanceText.sendKeys("Improve an existing feature");

        WaitUtils.visible(driver, additionalBenefit);
        additionalBenefit.sendKeys("Additional benefit");

        enterNeededByDate("15/10/2026");

        selectRating(4);

        String selectedFrequency = reusable.selectUsageFrequency("Daily");
        System.out.println("Selected frequency: " + selectedFrequency);

        reusable.selectRecommendation(true);

        String selectedHodApproval = selectHodApproval("I have approval");
        System.out.println("Selected HOD Approval: " + selectedHodApproval);

        ScreenshotIsAvailable.chooseAndUploadScreenshot("Enhancement", fileUpload);

        System.out.println("Enhancement feedback submitted successfully.");
    }

}
