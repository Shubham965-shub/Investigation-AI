package com.investigationai.qa.tests.feedback;

import org.testng.Assert;
import org.testng.annotations.Listeners;
import org.testng.annotations.Test;

import com.investigationai.qa.base.BaseTest;
import com.investigationai.qa.config.ConfigReader;
import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.modal.feedback.NewFeatureModal;
import com.investigationai.qa.pages.dashboard.DashboardPage;
import com.investigationai.qa.pages.login.LoginPage;
import com.investigationai.qa.reporting.ExtentReportListener;
import com.investigationai.qa.utils.TokenUtil;

@Listeners(ExtentReportListener.class)
public class NewFeatureModalTest extends BaseTest {

    private final String username=ConfigReader.get("username");
    private final String password=ConfigReader.get("password");

    @Test(description="User can submit new feature feedback when logged in.")
    public void verifyUserCanSubmitNewFeatureFeedback() {
        LoginPage loginPage=new LoginPage(DriverFactory.getDriver());
        loginPage.login(username,password);

        String token=TokenUtil.getAccessToken(DriverFactory.getDriver());
        Assert.assertNotNull(token,"User login failed, Token not found.");

        DashboardPage dashboardPage=new DashboardPage(DriverFactory.getDriver());
        NewFeatureModal newFeatureModal=dashboardPage.openNewFeatureModal();

        Assert.assertNotNull(newFeatureModal,"New Feature modal was not opened.");

        newFeatureModal.submitFeedback();

        Assert.assertTrue(true,"New Feature feedback submitted successfully.");
    }
}
