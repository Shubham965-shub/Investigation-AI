package com.investigationai.qa.pages.usermanagement;

import java.time.Duration;
import java.util.List;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.Select;
import org.openqa.selenium.support.ui.WebDriverWait;

import com.investigationai.qa.pages.BasePage;
import com.investigationai.qa.modal.usermanagement.AdminResetPasswordModal;
import com.investigationai.qa.pages.usermanagement.createuser.CreateUserModal;

public class UserManagementPage extends BasePage {

    private static final By PAGE_HEADING = By.xpath("//h1[normalize-space()='User Management']");
    private static final By ACCESS_DENIED_MESSAGE = By.xpath("//*[normalize-space()='This page is only available to Admin users.']");
    private static final By USER_ROWS = By.xpath("//table//tbody/tr");
    private static final By ROLE_DROPDOWNS = By.xpath("//table//tbody/tr//select[contains(@class,'field-value')]");

    private final WebDriver currentDriver;
    private final WebDriverWait wait;

    @FindBy(xpath = "//select")
    private WebElement roles;

    @FindBy(xpath = "//table")
    private WebElement userTable;

    @FindBy(xpath = "//table//tbody/tr")
    private List<WebElement> userRows;

    @FindBy(xpath = "//table//tbody/tr//select[contains(@class,'field-value')]")
    private List<WebElement> userDropdowns;

    @FindBy(xpath = "//button[normalize-space()='Reset Password']")
    private WebElement resetPasswordBtn;

    @FindBy(xpath = "//button[normalize-space()='Create User']")
    private WebElement createUserBtn;

    public UserManagementPage(WebDriver driver) {
        super(driver);
        currentDriver = driver;
        wait = new WebDriverWait(driver, Duration.ofSeconds(30));
        PageFactory.initElements(driver, this);
        wait.until(currentDriver -> !currentDriver.findElements(PAGE_HEADING).isEmpty()
                || !currentDriver.findElements(ACCESS_DENIED_MESSAGE).isEmpty());
    }

    public boolean isAccessDenied() {
        return !currentDriver.findElements(ACCESS_DENIED_MESSAGE).isEmpty();
    }

    public boolean isUserTableDisplayed() {
        return wait.until(ExpectedConditions.visibilityOf(userTable)).isDisplayed();
    }

    public int getUserRowCount() {
        wait.until(currentDriver -> !currentDriver.findElements(USER_ROWS).isEmpty());
        return userRows.size();
    }

    public List<WebElement> getUserRows() {
        return userRows;
    }

    public List<WebElement> getUserRoleDropdowns() {
        wait.until(currentDriver -> !currentDriver.findElements(ROLE_DROPDOWNS).isEmpty());
        return userDropdowns;
    }

    public WebElement getUserRow(int rowNumber) {
        return userRows.get(rowNumber);
    }

    public String getUserFullName(int rowNumber) {
        return userRows.get(rowNumber)
                .findElement(By.xpath("./td[1]"))
                .getText();
    }

    public String getUserEmail(int rowNumber) {
        return userRows.get(rowNumber)
                .findElement(By.xpath("./td[2]"))
                .getText();
    }

    public String getFirstUsernameWithPrefix(String prefix) {
        getUserRowCount();
        return userRows.stream()
                .map(row -> row.findElement(By.xpath("./td[2]")).getText().trim())
                .filter(username -> username.startsWith(prefix))
                .findFirst()
                .orElseThrow(() -> new org.openqa.selenium.NoSuchElementException(
                        "No existing QA user found with username prefix: " + prefix));
    }

    public String getUserRole(int rowNumber) {
        WebElement roleDropdown = userRows.get(rowNumber)
                .findElement(By.xpath("./td[3]//select"));

        return new Select(roleDropdown)
                .getFirstSelectedOption()
                .getText();
    }

    public String getUserRole(String email) {
        wait.until(currentDriver -> !currentDriver.findElements(
            By.xpath("//table//tbody/tr[td[2][normalize-space()='" + email + "']]")).isEmpty());
        for (WebElement row : userRows) {
            if (row.findElement(By.xpath("./td[2]")).getText().equals(email)) {
                WebElement roleDropdown = row.findElement(By.xpath("./td[3]//select"));
                return new Select(roleDropdown).getFirstSelectedOption().getText();
            }
        }
        throw new org.openqa.selenium.NoSuchElementException("No user found with email: " + email);
    }

    public void updateUserRole(String email, String role) {
        By roleDropdown = By.xpath("//table//tbody/tr[td[2][normalize-space()='" + email + "']]/td[3]//select");
        WebElement dropdown = wait.until(ExpectedConditions.elementToBeClickable(roleDropdown));
        new Select(dropdown).selectByVisibleText(role);
        wait.until(currentDriver -> {
            WebElement updatedDropdown = currentDriver.findElement(roleDropdown);
            return updatedDropdown.isEnabled()
                    && new Select(updatedDropdown).getFirstSelectedOption().getText().equals(role);
        });
    }

    public AdminResetPasswordModal openResetPassword(String email) {
        By resetButton = By.xpath("//table//tbody/tr[td[2][normalize-space()='" + email
                + "']]//button[normalize-space()='Reset Password']");
        wait.until(ExpectedConditions.elementToBeClickable(resetButton)).click();
        return new AdminResetPasswordModal(currentDriver);
    }

    public String getCreatedOn(int rowNumber) {
        return userRows.get(rowNumber)
                .findElement(By.xpath("./td[4]"))
                .getText();
    }

    public String getLastLoggedIn(int rowNumber) {
        return userRows.get(rowNumber)
                .findElement(By.xpath("./td[5]"))
                .getText();
    }

    public CreateUserModal clickCreateUser() {
        wait.until(ExpectedConditions.elementToBeClickable(createUserBtn)).click();
        return new CreateUserModal();
    }
}
