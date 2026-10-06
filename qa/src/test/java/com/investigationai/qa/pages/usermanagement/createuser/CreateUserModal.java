package com.investigationai.qa.pages.usermanagement.createuser;

import java.time.Duration;
import java.util.List;

import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.Select;
import org.openqa.selenium.support.ui.WebDriverWait;

import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.utils.WaitUtils;

public class CreateUserModal {

    public CreateUserModal() {
        PageFactory.initElements(DriverFactory.getDriver(), this);
    }

    @FindBy(xpath = "//div[@role='dialog']//input[@placeholder='e.g. Jane Doe']")
    private WebElement fullNameInput;

    @FindBy(xpath = "//div[@role='dialog']//input[@placeholder='e.g. jane.doe@strides.com']")
    private WebElement emailInput;

    @FindBy(xpath = "//div[@role='dialog']//select")
    private WebElement roleDropdown;

    @FindBy(xpath = "//div[@role='dialog']//input[@placeholder='At least 8 characters']")
    private WebElement passwordInput;

    @FindBy(xpath = "//div[@role='dialog']//button[normalize-space()='Create']")
    private WebElement createUserBtn;

    @FindBy(xpath = "//div[@role='dialog']//button[normalize-space()='Cancel']")
    private WebElement cancelBtn;

    public void createUser(String fullName, String email, String role, String password) {

        WaitUtils.visible(DriverFactory.getDriver(), cancelBtn);

        // Validate required fields
        if (isNullOrEmpty(fullName)
                || isNullOrEmpty(email)
                || isNullOrEmpty(role)
                || isNullOrEmpty(password)) {

            throw new IllegalArgumentException("All fields are required to create a user.");
        }

        // Validate email
        if (!isValidEmail(email)) {
            throw new IllegalArgumentException("Email must be a valid strides.com email address.");
        }

        // Validate password
        if (password.length() < 8) {
            throw new IllegalArgumentException("Password must be at least 8 characters long.");
        }

       
        fullNameInput.sendKeys(fullName);
        emailInput.sendKeys(email);
        new Select(roleDropdown).selectByVisibleText(role);
        passwordInput.sendKeys(password);

    
        createUserBtn.click();
    }

    public boolean isCreateUserModalDisplayed() {
        return fullNameInput.isDisplayed()
                && emailInput.isDisplayed()
                && roleDropdown.isDisplayed()
                && passwordInput.isDisplayed()
                && createUserBtn.isDisplayed()
                && cancelBtn.isDisplayed();
    }

    public List<String> getAvailableRoles() {
        return new Select(roleDropdown).getOptions().stream()
                .map(option -> option.getText().trim())
                .filter(role -> !role.isEmpty())
                .toList();
    }

    public String waitForCreateError() {
        return new WebDriverWait(DriverFactory.getDriver(), Duration.ofSeconds(10))
                .until(ExpectedConditions.visibilityOfElementLocated(
                        org.openqa.selenium.By.cssSelector("[role='dialog'] .error-banner")))
                .getText()
                .trim();
    }

    public void cancel() {
        cancelBtn.click();
    }

    public boolean isUserPresent(String email) {
        return new WebDriverWait(DriverFactory.getDriver(), Duration.ofSeconds(20))
            .until(driver -> driver.getPageSource().contains(email));
    }

    public boolean isValidEmail(String email) {
        if (email == null || email.isEmpty()) {
            return false;
        }

        String emailRegex = "^[A-Za-z0-9+_.-]+@strides\\.com$";

        return email.matches(emailRegex);
    }

    private boolean isNullOrEmpty(String value) {
        return value == null || value.trim().isEmpty();
    }
}
