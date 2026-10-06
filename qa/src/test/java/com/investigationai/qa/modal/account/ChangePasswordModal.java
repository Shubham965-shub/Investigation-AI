package com.investigationai.qa.modal.account;

import java.time.Duration;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

public class ChangePasswordModal {

    private static final By DIALOG = By.xpath("//div[@role='dialog']");

    private final WebDriver driver;
    private final WebDriverWait wait;

    @FindBy(xpath = "(//div[@role='dialog']//input[@type='password'])[1]")
    private WebElement currentPasswordInput;

    @FindBy(xpath = "(//div[@role='dialog']//input[@type='password'])[2]")
    private WebElement newPasswordInput;

    @FindBy(xpath = "(//div[@role='dialog']//input[@type='password'])[3]")
    private WebElement confirmPasswordInput;

    @FindBy(xpath = "//div[@role='dialog']//button[normalize-space()='Change Password']")
    private WebElement changePasswordButton;

    @FindBy(xpath = "//div[@role='dialog']//button[normalize-space()='Cancel']")
    private WebElement cancelButton;

    public ChangePasswordModal(WebDriver driver) {
        this.driver = driver;
        wait = new WebDriverWait(driver, Duration.ofSeconds(10));
        PageFactory.initElements(driver, this);
        wait.until(ExpectedConditions.visibilityOfElementLocated(DIALOG));
    }

    public boolean isDisplayed() {
        return currentPasswordInput.isDisplayed()
                && newPasswordInput.isDisplayed()
                && confirmPasswordInput.isDisplayed()
                && changePasswordButton.isDisplayed()
                && cancelButton.isDisplayed();
    }

    public void changePassword(String currentPassword, String newPassword) {
        currentPasswordInput.sendKeys(currentPassword);
        newPasswordInput.sendKeys(newPassword);
        confirmPasswordInput.sendKeys(newPassword);
        changePasswordButton.click();
        wait.until(ExpectedConditions.invisibilityOfElementLocated(DIALOG));
    }

    public void cancel() {
        cancelButton.click();
        wait.until(ExpectedConditions.invisibilityOfElementLocated(DIALOG));
    }
}
