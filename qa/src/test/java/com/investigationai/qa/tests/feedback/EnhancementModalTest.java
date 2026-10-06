package com.investigationai.qa.tests.feedback;


import org.testng.Assert;
import org.testng.annotations.Listeners;
import org.testng.annotations.Test;

import com.investigationai.qa.base.BaseTest;
import com.investigationai.qa.config.ConfigReader;
import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.modal.feedback.EnhancementModal;
import com.investigationai.qa.pages.dashboard.DashboardPage;
import com.investigationai.qa.pages.login.LoginPage;
import com.investigationai.qa.reporting.ExtentReportListener;
import com.investigationai.qa.utils.TokenUtil;

@Listeners(ExtentReportListener.class)
public class EnhancementModalTest extends BaseTest {

    private final String username = ConfigReader.get("username");
    private final String password = ConfigReader.get("password");

    @Test(description = "User can submit enhancement feedback when logged in.")
    public void verifyUserCanSubmitEnhancementFeedback() {
        LoginPage loginPage = new LoginPage(DriverFactory.getDriver());
        loginPage.login(username, password);

        String token = TokenUtil.getAccessToken(DriverFactory.getDriver());
        Assert.assertNotNull(token, "User login failed, Token not found.");

        DashboardPage dashboardPage = new DashboardPage(DriverFactory.getDriver());
        EnhancementModal enhancementModal = dashboardPage.openEnhancementModal();

        Assert.assertNotNull(enhancementModal, "Enhancement modal was not opened.");

        enhancementModal.submitFeedback();

        Assert.assertTrue(true, "Enhancement feedback submitted successfully.");
    }
}
