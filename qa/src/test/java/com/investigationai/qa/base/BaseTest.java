package com.investigationai.qa.base;

import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.pages.dashboard.DashboardPage;
import com.investigationai.qa.pages.login.LoginPage;
import com.investigationai.qa.config.ConfigReader;
import com.investigationai.qa.utils.ScreenshotUtils;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeMethod;
import org.testng.ITestResult;

public abstract class BaseTest {
    protected LoginPage loginPage;
    protected DashboardPage dashboardPage;

    @BeforeMethod(alwaysRun = true)
    public void setUp() {
        DriverFactory.startDriver(Thread.currentThread().getName());
        loginPage = new LoginPage(DriverFactory.getDriver()).openLoginPage();
        System.out.println("Base Test loginpage=" + loginPage);
        dashboardPage = new DashboardPage(DriverFactory.getDriver());
    }

    @AfterMethod(alwaysRun = true)
    public void tearDown(ITestResult result) {
        if (!result.isSuccess()) {
            String screenshotPath = ScreenshotUtils.capture(DriverFactory.getDriver(), result.getMethod().getMethodName());
            if (!screenshotPath.isBlank()) {
                result.setAttribute("failureScreenshot", screenshotPath);
            }
        }
        if (!Boolean.parseBoolean(ConfigReader.get("keepBrowserOpen"))) {
            DriverFactory.quitDriver();
        }
    }
}
