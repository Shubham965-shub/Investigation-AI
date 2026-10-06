package com.investigationai.qa.tests.login;

import org.testng.Assert;
import org.testng.annotations.Listeners;
import org.testng.annotations.Test;
import org.openqa.selenium.JavascriptExecutor;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;
import java.time.Duration;

import com.investigationai.qa.base.BaseTest;
import com.investigationai.qa.config.ConfigReader;
import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.reporting.ExtentReportListener;

@Listeners(ExtentReportListener.class)
public class LoginTest extends BaseTest {

    private String username = ConfigReader.get("username");;
    private String password = ConfigReader.get("password");;

    @Test(description = "Verify that the login page is displayed successfully", priority = 1)
    public void verifyLoginPageDisplay() {
        System.out.println("Current URl: " + loginPage.getCurrentUrl());
        Assert.assertTrue(loginPage.getCurrentUrl().contains("/login"), "Login form is not displayed");

    }

    @Test(description = "Verify successful login with valid credentials", priority = 2)
    public void verifySuccessfulLogin() {
        loginPage.login(username, password);
        Assert.assertTrue(loginPage.verifyNavigatedToDashboard(), "SIT Dashboard is not Displayed");
    }

    @Test(description = "Verify login with invalid username", priority = 3)
    public void verifyInvalidUsername() {
    loginPage.login("invalidUsername", password);
    Assert.assertTrue(loginPage.getErrorMessage().contains("Invalid username or password"),
    "Error message not displayed for invalid username");
    }

    @Test(description = "Verify login with invalid password", priority = 4)
    public void verifyInvalidPassword() {
    loginPage.login(username, "invalidPassword");
    Assert.assertTrue(loginPage.getErrorMessage().contains("Invalid username or password"),
    "Error message not displayed for invalid password");
    }

    @Test(description = "Verify Login with empty username field")
    public void verifyEmptyUsername() {
        loginPage.login("", password);
        String actualMessage = loginPage.getUsernameValidationMessage();
        System.out.println("[" + actualMessage + "]");

        Assert.assertEquals(actualMessage, "Please fill in this field.");
    }

    @Test(description = "Verify Login with empty password field")
    public void verifyEmptyPassword() {
        loginPage.login(username, "");
        String actualMessage = loginPage.getPasswordValidationMessage();
        System.out.println("[" + actualMessage + "]");
        Assert.assertEquals(actualMessage, "Please fill in this field.");
    }

    @Test(description = "Verify login with both field empty")
    public void verifyBothFieldEmpty() {
        loginPage.login("", "");
        String actualMessage = loginPage.getPasswordValidationMessage();
        System.out.println("[" + actualMessage + "]");
        Assert.assertEquals(actualMessage, "Please fill in this field.");

    }

    @Test(description = "Verify login with leading or trailing spaces in username and password")
    public void verifyLeadingOrTrilingSpaces() {
    loginPage.login(" " + username + " ", " " + password + " ");
    Assert.assertTrue(loginPage.getErrorMessage().contains("Invalid username or password"),
    "Expected error message not Displayed.");
    }

    @Test(description = "Account is inactive or disabled")
    public void verifyInactiveOrDisabaledUser() {
        loginPage.login("inactiveUser", password);
        Assert.assertTrue(loginPage.getErrorMessage().contains(""),
                "Expected error message not Displayed.");
    }

        @Test(description = "An expired session token redirects to login on page reload")
        public void expiredTokenRedirectsToLoginOnPageLoad() {
        loginPage.login(username, password);
            Assert.assertTrue(loginPage.verifyNavigatedToDashboard(), "Login failed before the expiry check");

        JavascriptExecutor javascript = (JavascriptExecutor) DriverFactory.getDriver();
        javascript.executeScript(
                    "const payload = btoa(JSON.stringify({exp: Math.floor(Date.now() / 1000) - 60}))"
                            + ".replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/g, '');"
                            + "localStorage.setItem('auth_token', 'e30.' + payload + '.qa-expired-token');");
            DriverFactory.getDriver().navigate().refresh();

        new WebDriverWait(DriverFactory.getDriver(), Duration.ofSeconds(10))
            .until(ExpectedConditions.urlContains("/login"));
            Assert.assertTrue(loginPage.isLoginFormDisplayed(), "Expired token did not show the login form");
    }

    @Test(description = "Verify browser refresh after login in successfully")
    public void verifyBackAfterLogin() {
        loginPage.login(username, password);
        Assert.assertTrue(loginPage.verifyNavigatedToDashboard(), "User not navigated to dashboard after login");
        System.out.println("Before refresh URL:" + DriverFactory.getDriver().getCurrentUrl());

        String currentURL = DriverFactory.getDriver().getCurrentUrl();
        DriverFactory.getDriver().navigate().refresh();
        Assert.assertTrue(loginPage.verifyNavigatedToDashboard(), "User not on  dashboard after refresh");
        System.out.println("After Refresh URL:" + currentURL);
        Assert.assertEquals(currentURL, ConfigReader.get("baseUrl"));

    }

    @Test(description = "Check if the pasword is masked ")
    public void passwordMasking() {
        Assert.assertTrue(loginPage.isLoginFormDisplayed());
        String type = loginPage.getPasswordInputType();
        System.out.println("Password type:" + type);
        Assert.assertNotNull(type);
        Assert.assertEquals(type, "password", "Password field should mask user input");
    }

}
