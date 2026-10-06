package com.investigationai.qa.tests;

import com.investigationai.qa.base.BaseTest;
import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.pages.login.LoginPage;

import org.testng.annotations.Test;

import static org.testng.Assert.assertTrue;

public class SanityTest extends BaseTest {
    @Test(groups = "sanity")
    public void loginPageIsAvailable() {
        LoginPage loginPage = new LoginPage(DriverFactory.getDriver()).openLoginPage();
        assertTrue(loginPage.isLoginFormDisplayed(), "Login form is not available");
    }
}