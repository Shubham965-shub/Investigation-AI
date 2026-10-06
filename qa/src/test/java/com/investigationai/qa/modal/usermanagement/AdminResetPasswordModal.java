package com.investigationai.qa.modal.usermanagement;

import java.time.Duration;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

public class AdminResetPasswordModal {

    private static final By DIALOG = By.xpath("//div[@role='dialog']");

    private final WebDriverWait wait;

    @FindBy(xpath = "//div[@role='dialog']//input[@placeholder='At least 8 characters']")
    private WebElement newPasswordInput;

    @FindBy(xpath = "(//div[@role='dialog']//input[@type='password'])[2]")
    private WebElement confirmPasswordInput;

    @FindBy(xpath = "//div[@role='dialog']//button[normalize-space()='Reset Password']")
    private WebElement resetPasswordButton;

    @FindBy(xpath = "//div[@role='dialog']//button[normalize-space()='Cancel']")
    private WebElement cancelButton;

    public AdminResetPasswordModal(WebDriver driver) {
        wait = new WebDriverWait(driver, Duration.ofSeconds(10));
        PageFactory.initElements(driver, this);
        wait.until(ExpectedConditions.visibilityOfElementLocated(DIALOG));
    }

    public boolean isDisplayed() {
        return newPasswordInput.isDisplayed()
                && confirmPasswordInput.isDisplayed()
                && resetPasswordButton.isDisplayed()
                && cancelButton.isDisplayed();
    }

    public void resetPassword(String newPassword) {
        newPasswordInput.sendKeys(newPassword);
        confirmPasswordInput.sendKeys(newPassword);
        resetPasswordButton.click();
        wait.until(ExpectedConditions.invisibilityOfElementLocated(DIALOG));
    }

    public void cancel() {
        cancelButton.click();
        wait.until(ExpectedConditions.invisibilityOfElementLocated(DIALOG));
    }
}
