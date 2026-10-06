package com.investigationai.qa.pages.login;

import java.util.Map;

import org.openqa.selenium.JavascriptExecutor;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;

import com.investigationai.qa.config.ConfigReader;
import com.investigationai.qa.pages.BasePage;
import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.utils.ElementUtil;
import com.investigationai.qa.utils.ScreenshotUtils;
import com.investigationai.qa.utils.WaitUtils;

public class LoginPage extends BasePage {

    private final ElementUtil elementUtil;

    @FindBy(id = "username")
    private WebElement usernameInput;

    @FindBy(id = "password")
    private WebElement passwordInput;

    @FindBy(xpath = "//button[@type='submit']")
    private WebElement loginButton;

    @FindBy(css = "p.text-red-400")
    private WebElement errorMessage;

    @FindBy(xpath = "//h1[contains(.,'SIT Dashboard')]")
    private WebElement dashboardPage;

    public LoginPage(WebDriver driver) {
        super(driver);
        elementUtil = new ElementUtil(driver);
    }

    public LoginPage openLoginPage() {
        open("/login");
        waitForPageElement(usernameInput);
        return this;
    }

    public boolean isLoginFormDisplayed() {
        return elementUtil.isDisplayed(usernameInput)
                && elementUtil.isDisplayed(passwordInput)
                && elementUtil.isDisplayed(loginButton);
    }

    public LoginPage login(String username, String password) {
        enterCredentials(username, password);
        submit();
        return this;
    }

    public LoginPage enterCredentials(String username, String password) {
        elementUtil.type(usernameInput, username);
        elementUtil.type(passwordInput, password);
        return this;
    }

    public LoginPage submit() {
        elementUtil.click(loginButton);
        System.out.println("After Login URL: " + driver.getCurrentUrl());
        return this;
    }

    public boolean verifyNavigatedToDashboard() {
        try {
            WaitUtils.visible(driver, dashboardPage);

            String currentUrl = driver.getCurrentUrl();
            String baseUrl = ConfigReader.get("baseUrl");
            String dashboardText = elementUtil.getText(dashboardPage).trim();

            System.out.println("Current URL: " + currentUrl);
            System.out.println("Expected Base URL: " + baseUrl);
            System.out.println("Dashboard Text: [" + dashboardText + "]");

            return dashboardText.contains("SIT Dashboard") && currentUrl.startsWith(baseUrl);

        } catch (Exception e) {
            e.printStackTrace();
            return false;
        }
    }

    public String getErrorMessage() {
        ScreenshotUtils.capture(
                DriverFactory.getDriver(),
                "Error Message");

        WaitUtils.visible(
                DriverFactory.getDriver(),
                errorMessage);

        return elementUtil.getText(errorMessage).trim();
    }

    public String getUsernameValidationMessage() {
        return elementUtil.getAttribute(
                usernameInput,
                "validationMessage");
    }

    public String getPasswordValidationMessage() {
        return elementUtil.getAttribute(
                passwordInput,
                "validationMessage");
    }

    public String getPasswordInputType() {
        return elementUtil.getAttribute(
                passwordInput,
                "type");
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getLocalStorage() {
        JavascriptExecutor js = (JavascriptExecutor) driver;

        return (Map<String, Object>) js.executeScript(
                "var items={};" +
                        "for(var i=0;i<localStorage.length;i++){" +
                        "items[localStorage.key(i)]=localStorage.getItem(localStorage.key(i));" +
                        "}" +
                        "return items;");
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getSessionStorage() {
        JavascriptExecutor js = (JavascriptExecutor) driver;

        return (Map<String, Object>) js.executeScript(
                "var items={};" +
                        "for(var i=0;i<sessionStorage.length;i++){" +
                        "items[sessionStorage.key(i)]=sessionStorage.getItem(sessionStorage.key(i));" +
                        "}" +
                        "return items;");
    }

    public LoginPage waitForSessionTimeout() {
        JavascriptExecutor js = (JavascriptExecutor) driver;

        js.executeScript("window.localStorage.clear();");
        js.executeScript("window.sessionStorage.clear()");

        driver.manage().deleteAllCookies();

        elementUtil.refreshPage();

        WaitUtils.urlContains(driver, "/login");

        return this;
    }

    public String getCurrentUrl() {
        return driver.getCurrentUrl();
    }
}
