package com.investigationai.qa.tests;

import org.testng.Assert;
import org.testng.annotations.Test;

import com.investigationai.qa.base.BaseTest;
import com.investigationai.qa.config.ConfigReader;
import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.pages.login.LoginPage;

public class SmokeTest extends BaseTest {

    @Test(groups = "smoke")
    public void validUserCanLoginAndReachDashboard() {

        String username = ConfigReader.get("username");
        String password = ConfigReader.get("password");

        LoginPage loginPage =new LoginPage(DriverFactory.getDriver()).openLoginPage();
        loginPage.login(username, password);

        System.out.println("Current URL after login: "+ loginPage.getCurrentUrl());
        Assert.assertTrue(loginPage.verifyNavigatedToDashboard(),"Login did not navigate to the Dashboard Page"
        );
    }
}
