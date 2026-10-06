package com.investigationai.qa.tests.feedback;

import org.testng.Assert;
import org.testng.annotations.Listeners;
import org.testng.annotations.Test;

import com.investigationai.qa.base.BaseTest;
import com.investigationai.qa.config.ConfigReader;
import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.modal.feedback.FeedBackModal;
import com.investigationai.qa.pages.dashboard.DashboardPage;
import com.investigationai.qa.pages.login.LoginPage;
import com.investigationai.qa.reporting.ExtentReportListener;
import com.investigationai.qa.utils.TokenUtil;

@Listeners(ExtentReportListener.class)
public class GeneralFeedbackTest extends BaseTest {
    private final String username = ConfigReader.get("username");
    private final String password = ConfigReader.get("password");

    @Test(description = "User can see the submit feedback button if user is logged in.")
    public void verifyUserCanSubmitFeedback() {
        LoginPage loginPage = new LoginPage(DriverFactory.getDriver());
        loginPage.login(username, password);
        String token=TokenUtil.getAccessToken(DriverFactory.getDriver());
        Assert.assertNotNull(token,"User login failed,Token Not found.");
        DashboardPage dashboardPage = new DashboardPage(DriverFactory.getDriver());
        FeedBackModal feedBackModal = dashboardPage.openFeedbackModal();
        feedBackModal.submitFeedback();
    }

}
