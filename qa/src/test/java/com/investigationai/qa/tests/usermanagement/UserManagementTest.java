package com.investigationai.qa.tests.usermanagement;

import java.time.Duration;
import java.util.List;
import java.util.UUID;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.testng.Assert;
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.Test;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

import com.investigationai.qa.base.BaseTest;
import com.investigationai.qa.config.ConfigReader;
import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.modal.usermanagement.AdminResetPasswordModal;
import com.investigationai.qa.pages.usermanagement.UserManagementPage;
import com.investigationai.qa.pages.usermanagement.createuser.CreateUserModal;

public class UserManagementTest extends BaseTest {

    private UserManagementPage userManagementPage;
    private String createdUsername;
    private String createdPassword;

    @BeforeMethod
    public void openUserManagement() {
        String username = ConfigReader.get("username");
        String password = ConfigReader.get("password");
        loginPage.login(username, password);
        Assert.assertTrue(loginPage.verifyNavigatedToDashboard(), "Login failed - Dashboard was not displayed");
        WebDriver driver = DriverFactory.getDriver();
        new WebDriverWait(driver, Duration.ofSeconds(15))
                .until(ExpectedConditions.elementToBeClickable(By.cssSelector("button[aria-label='User Management']")))
                .click();
        userManagementPage = new UserManagementPage(driver);
    }

    @Test(groups = "smoke", description = "Admin can open User Management and view the user table")
    public void adminCanOpenUserManagementPage() {
        verifyUserTableIsDisplayed();
    }

    @Test(groups = "sanity", description = "Admin can reset an existing QA user's password")
    public void adminCanResetExistingAutomationUserPassword() {
        String targetUsername = System.getProperty("qa.reset.username", "").trim();
        if (targetUsername.isEmpty()) {
            targetUsername = userManagementPage.getFirstUsernameWithPrefix("automation.test.");
        }
        String resetPassword = "QaReset@Test2026";
        AdminResetPasswordModal resetPasswordModal = userManagementPage.openResetPassword(targetUsername);

        Assert.assertTrue(resetPasswordModal.isDisplayed(), "Admin Reset Password modal is not displayed");
        resetPasswordModal.resetPassword(resetPassword);

        dashboardPage.logout();
        new WebDriverWait(DriverFactory.getDriver(), Duration.ofSeconds(10))
                .until(ExpectedConditions.visibilityOfElementLocated(By.id("username")));
        loginPage.login(targetUsername, resetPassword);
        new WebDriverWait(DriverFactory.getDriver(), Duration.ofSeconds(20))
                .until(driver -> !driver.getCurrentUrl().contains("/login")
                        && !driver.findElements(By.tagName("h1")).isEmpty());
        Assert.assertTrue(DriverFactory.getDriver().getCurrentUrl().startsWith(ConfigReader.get("baseUrl")),
                "QA user could not log in with the reset password");
    }

    @Test(groups = "sanity", description = "Admin can manage users and non-admin access is restricted")
    public void adminCanManageUsersAndRestrictNonAdminAccess() {
        verifyUserTableIsDisplayed();
        verifyUsersAreDisplayed();
        verifyUserRoleDropdownsAreDisplayed();
        verifyFirstUserDetailsAreAvailable();
        verifyExistingUserCannotBeCreated();
        verifyUserCanBeCreated();
    }

    private void verifyUserTableIsDisplayed() {
        Assert.assertTrue(userManagementPage.isUserTableDisplayed(), "User table is not displayed");
    }

    private void verifyUsersAreDisplayed() {
        Assert.assertTrue(userManagementPage.getUserRowCount() > 0, "No users are displayed in the user table");
    }

    private void verifyUserRoleDropdownsAreDisplayed() {
        Assert.assertTrue(userManagementPage.getUserRoleDropdowns().size() > 0, "No user role dropdowns are displayed");
    }

    private void verifyUserCanBeCreated() {
        CreateUserModal createUserModal = userManagementPage.clickCreateUser();
        Assert.assertTrue(createUserModal.isCreateUserModalDisplayed(), "Create User modal is not displayed");
        String fullName = "Automation Test User";
        createdUsername = "automation.test." +UUID.randomUUID().toString().substring(0, 8) +"@strides.com";
        createdPassword = "Test@12345";
        List<String> availableRoles = createUserModal.getAvailableRoles();
        List<String> requiredRoles = List.of("Admin", "CXO", "SIT", "Investigator");

        for (String requiredRole : requiredRoles) {
            Assert.assertTrue(availableRoles.stream().anyMatch(role -> role.equalsIgnoreCase(requiredRole)),
                    "Create User modal is missing the " + requiredRole + " role");
        }

        String investigatorRole = findRole(availableRoles, "Investigator");
        createUserModal.createUser(fullName, createdUsername, investigatorRole, createdPassword);
        Assert.assertTrue(createUserModal.isUserPresent(createdUsername),
                "Created user was not found: " + createdUsername);

        for (String requiredRole : requiredRoles) {
            String role = findRole(availableRoles, requiredRole);
            userManagementPage.updateUserRole(createdUsername, role);
            Assert.assertEquals(userManagementPage.getUserRole(createdUsername), role,
                    "User role was not updated to " + role);
        }
        userManagementPage.updateUserRole(createdUsername, investigatorRole);
        Assert.assertEquals(userManagementPage.getUserRole(createdUsername), investigatorRole,
                "Test user should be left with a non-admin role");

        createdPassword = "Reset@12345";
        AdminResetPasswordModal resetPasswordModal = userManagementPage.openResetPassword(createdUsername);
        Assert.assertTrue(resetPasswordModal.isDisplayed(), "Admin Reset Password modal is not displayed");
        resetPasswordModal.resetPassword(createdPassword);

        verifyNonAdminCannotAccessUserManagement();
    }

    private void verifyExistingUserCannotBeCreated() {
        String existingUsername = userManagementPage.getUserEmail(0);
        CreateUserModal createUserModal = userManagementPage.clickCreateUser();
        createUserModal.createUser(
                "Duplicate User Attempt",
                existingUsername,
                findRole(createUserModal.getAvailableRoles(), "Investigator"),
                "Test@12345");

        Assert.assertTrue(createUserModal.waitForCreateError().toLowerCase().contains("already in use"),
                "Creating an existing username should show an already-in-use error");
        createUserModal.cancel();
    }

    private void verifyNonAdminCannotAccessUserManagement() {
        WebDriver driver = DriverFactory.getDriver();
        driver.findElement(By.cssSelector("button[aria-label='Account menu']")).click();
        new WebDriverWait(driver, Duration.ofSeconds(10))
                .until(ExpectedConditions.elementToBeClickable(By.xpath("//button[normalize-space()='Log out']")))
                .click();
        new WebDriverWait(driver, Duration.ofSeconds(10))
                .until(ExpectedConditions.visibilityOfElementLocated(By.id("username")));

        loginPage.login(createdUsername, createdPassword);
        new WebDriverWait(driver, Duration.ofSeconds(20))
                .until(currentDriver -> !currentDriver.getCurrentUrl().contains("/login")
                        && !currentDriver.findElements(By.tagName("h1")).isEmpty());
        Assert.assertTrue(driver.getCurrentUrl().startsWith(ConfigReader.get("baseUrl")),
                "Created non-admin user could not log in");
        Assert.assertTrue(driver.findElements(By.cssSelector("button[aria-label='User Management']")).isEmpty(),
                "User Management navigation should be hidden for non-admin users");

        String baseUrl = ConfigReader.get("baseUrl").replaceAll("/+$", "");
        driver.get(baseUrl + "/user-management");
        UserManagementPage restrictedPage = new UserManagementPage(driver);
        Assert.assertTrue(restrictedPage.isAccessDenied(),
                "Direct User Management access should be denied for non-admin users");
    }

    private String findRole(List<String> availableRoles, String expectedRole) {
        return availableRoles.stream()
                .filter(role -> role.equalsIgnoreCase(expectedRole))
                .findFirst()
                .orElseThrow(() -> new AssertionError("Role is not available: " + expectedRole));
    }

    private void verifyFirstUserDetailsAreAvailable() {
        Assert.assertTrue(userManagementPage.getUserRowCount() > 0, "No users available in the table");
        String fullName = userManagementPage.getUserFullName(0);
        String email = userManagementPage.getUserEmail(0);
        String role = userManagementPage.getUserRole(0);
        Assert.assertFalse(fullName.isBlank(), "First user's full name is empty");
        Assert.assertFalse(email.isBlank(), "First user's email is empty");
        Assert.assertFalse(role.isBlank(), "First user's role is empty");
    }
}
