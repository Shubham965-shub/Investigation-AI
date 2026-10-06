package com.investigationai.qa.pages.dashboard;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.Select;
import org.openqa.selenium.support.ui.WebDriverWait;

import com.investigationai.qa.driver.DriverFactory;
import com.investigationai.qa.exception.AccountNotFoundException;
import com.investigationai.qa.modal.feedback.BugIssueModal;
import com.investigationai.qa.modal.feedback.EnhancementModal;
import com.investigationai.qa.modal.feedback.FeedBackModal;
import com.investigationai.qa.modal.feedback.NewFeatureModal;
import com.investigationai.qa.modal.account.ChangePasswordModal;
import com.investigationai.qa.utils.WaitUtils;

public class DashboardPage {

    private static final By DASHBOARD_TITLE = By.cssSelector("h1.ac-title");
    private static final By EVENT_TYPE_CARDS = By.cssSelector(
            ".ac-kpi-card.event-deviation, .ac-kpi-card.event-oos, .ac-kpi-card.event-oot, .ac-kpi-card.event-mc");
        private static final By KPI_CARDS = By.cssSelector(".ac-kpi-row .ac-kpi-card");
        private static final By ESCALATION_CARDS = By.cssSelector(
            ".ac-status-card.l1, .ac-status-card.l2, .ac-status-card.l3, .ac-status-card.l4, .ac-status-card.l5");
    private static final By ACCOUNT_MENU_BUTTON = By.cssSelector("button[aria-label='Account menu']");

    @FindBy(xpath = "//div[contains(text(),'OPEN INVESTIGATIONS') or contains(text(),'Open Investigations')]")
    private WebElement openInvestigationCard;

    @FindBy(xpath = "//div[contains(@class,'ac-kpi-card event-deviation')]")
    private WebElement deviationCard;

    @FindBy(xpath = "//div[@class='ac-kpi-card event-oos ']")
    private WebElement oosCard;

    @FindBy(xpath = "//div[@class='ac-kpi-card event-oot ']")
    private WebElement ootCard;

    @FindBy(xpath = "//div[@class='ac-kpi-card event-mc ']")
    private WebElement marketComplaintCard;

    @FindBy(xpath = "//span[normalize-space()='Athena']/preceding-sibling::img[1]")
    private WebElement stridesLogo;

    @FindBy(xpath = "//span[normalize-space()='Athena']")
    private WebElement athenaTitle;

    @FindBy(xpath = "//img[@src='/src/assets/icons/athena-logo.svg']")
    private WebElement athenaLogo;

    @FindBy(xpath = "//button[@aria-label='Share feedback']")
    private WebElement feedbackBtn;

    @FindBy(xpath = "//button[@aria-label='Toggle dark mode']//img")
    private WebElement themeToggle;

    @FindBy(xpath = "//span[contains(@style,'font-size')]")
    private WebElement loggedInUserName;

    @FindBy(xpath = "//label[normalize-space()='View dashboard as (demo)']/following-sibling::select")
    private WebElement accountDropdown;

    @FindBy(xpath = "//button[@title='User Management']//img")
    private WebElement userManagementIcon;

    @FindBy(xpath = "//*[contains(text(),'Signed in as')]")
    private WebElement signedInAsLabel;

    @FindBy(xpath = "//p[contains(text(),'@strides.com')]")
    private WebElement signedInEmail;

    @FindBy(xpath = "//button[contains(text(),'Log out')]")
    private WebElement logoutBtn;

    @FindBy(xpath = "//button[@aria-label='Account menu']")
    private WebElement profileIcon;

    @FindBy(xpath = "//button[.//span[contains(.,'Bug / Data issue')]]")
    private WebElement bugIssueBtn;

    @FindBy(xpath = "")
    private WebElement logout;

    @FindBy(css = "h1.ac-title")
    private WebElement dashboardPage;

    public DashboardPage(WebDriver driver) {
        PageFactory.initElements(driver, this);
    }

    public boolean isDashboardPageDisplayed() {
        try {
            WebDriver driver = DriverFactory.getDriver();
            WebElement title = new WebDriverWait(driver, Duration.ofSeconds(20))
                    .until(ExpectedConditions.visibilityOfElementLocated(DASHBOARD_TITLE));
            String dashboardText = dashboardPage.getText().trim();
            return title.isDisplayed() && (dashboardText.equalsIgnoreCase("SIT Dashboard")
                    || dashboardText.equalsIgnoreCase("Action Center")
                    || dashboardText.startsWith("Action Center - Investigator View"));
        } catch (Exception e) {
            return false;
        }
    }

    public String getDashboardTitle() {
        return new WebDriverWait(DriverFactory.getDriver(), Duration.ofSeconds(20))
                .until(ExpectedConditions.visibilityOfElementLocated(DASHBOARD_TITLE))
                .getText()
                .trim();
    }

    public boolean isOpenInvestigationsCardDisplayed() {
        WebDriver driver = DriverFactory.getDriver();
        WebElement cardHeader = new WebDriverWait(driver, Duration.ofSeconds(20))
                .until(ExpectedConditions.visibilityOfElementLocated(
                        By.xpath("//div[contains(@class,'ac-kpi-card-header') and normalize-space()='OPEN INVESTIGATIONS']")));
        return cardHeader.isDisplayed();
    }

    public boolean areEventTypeCardsDisplayed() {
        WebDriver driver = DriverFactory.getDriver();
        List<WebElement> cards = new WebDriverWait(driver, Duration.ofSeconds(20))
                .until(currentDriver -> {
                    List<WebElement> foundCards = currentDriver.findElements(EVENT_TYPE_CARDS);
                    return foundCards.size() == 4 ? foundCards : null;
                });
        return cards.stream().allMatch(WebElement::isDisplayed);
    }

    public Map<String, Integer> getKpiCounts() {
        WebDriver driver = DriverFactory.getDriver();
        List<WebElement> cards = new WebDriverWait(driver, Duration.ofSeconds(20))
                .until(currentDriver -> {
                    List<WebElement> foundCards = currentDriver.findElements(KPI_CARDS);
                    return foundCards.size() >= 4 ? foundCards : null;
                });
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (WebElement card : cards) {
            String label = card.findElement(By.cssSelector(".ac-kpi-card-header")).getText().trim();
            String value = card.findElement(By.cssSelector(".ac-kpi-card-count")).getText().trim();
            counts.put(label.toUpperCase(), Integer.parseInt(value));
        }
        return counts;
    }

    public Map<String, Integer> getEscalationCounts() {
        WebDriver driver = DriverFactory.getDriver();
        List<WebElement> cards = new WebDriverWait(driver, Duration.ofSeconds(20))
                .until(currentDriver -> {
                    List<WebElement> foundCards = currentDriver.findElements(ESCALATION_CARDS);
                    return foundCards.size() == 5 ? foundCards : null;
                });
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (WebElement card : cards) {
            String key = card.getAttribute("class").replaceAll(".*\\bl([1-5])\\b.*", "L$1");
            String value = card.findElement(By.cssSelector(".ac-status-count")).getText().trim();
            counts.put(key, Integer.parseInt(value));
        }
        return counts;
    }

    public boolean isAccountMenuDisplayed() {
        WebDriver driver = DriverFactory.getDriver();
        return new WebDriverWait(driver, Duration.ofSeconds(20))
                .until(ExpectedConditions.visibilityOfElementLocated(ACCOUNT_MENU_BUTTON))
                .isDisplayed();
    }

    public boolean isStridesLogoDisplayed() {
        if (stridesLogo != null && stridesLogo.isDisplayed()) {
            return true;
        } else {
            return false;
        }
    }

    public boolean isAthenaLogoDisplayed() {
        if (athenaLogo != null && athenaLogo.isDisplayed() && athenaTitle != null && athenaTitle.isDisplayed()) {
            return true;
        } else {
            return false;
        }
    }

    public void closeFeedback() {
        WebElement closeBtn = DriverFactory.getDriver().findElement(By.xpath(
                "//button[@class=\"ring-offset-background focus:ring-ring data-[state=open]:bg-accent data-[state=open]:text-muted-foreground absolute top-4 right-4 rounded-xs opacity-70 transition-opacity hover:opacity-100 focus:ring-2 focus:ring-offset-2 focus:outline-hidden disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4\"]"));
        if (closeBtn != null && closeBtn.isDisplayed()) {
            closeBtn.click();
        }
    }

    public FeedBackModal openFeedbackModal() {
        WaitUtils.visible(DriverFactory.getDriver(), feedbackBtn);
        if (feedbackBtn != null && feedbackBtn.isDisplayed()) {
            feedbackBtn.click();
            return new FeedBackModal(DriverFactory.getDriver());
        }
        throw new NoSuchElementException("Feedback button is not displayed.");
    }

    public BugIssueModal openBugFeedbackModel() {
        WebElement feedbackBtn = DriverFactory.getDriver().findElement(By.xpath("//button[contains(.,'Feedback')]"));
        WaitUtils.visible(DriverFactory.getDriver(), feedbackBtn);
        System.out.println("Feedback button: " + feedbackBtn.getText());
        feedbackBtn.click();
        WaitUtils.visible(DriverFactory.getDriver(), bugIssueBtn);
        System.out.println("Bug / Data issue button: " + bugIssueBtn.getText());
        bugIssueBtn.click();
        return new BugIssueModal(DriverFactory.getDriver());
    }

    public EnhancementModal openEnhancementModal() {
        WebDriver driver = DriverFactory.getDriver();
        WebElement feedbackButton = driver.findElement(By.xpath("//button[contains(.,'Feedback')]"));
        WaitUtils.visible(driver, feedbackButton);
        System.out.println("Feedback button: " + feedbackButton.getText());
        feedbackButton.click();
        WebElement openEnhanceBtn = driver.findElement(By.xpath("//button[.//span[contains(.,'Enhancement')]]"));
        WaitUtils.visible(driver, openEnhanceBtn);
        System.out.println("Enhancement Text:" + openEnhanceBtn.getText());
        openEnhanceBtn.click();
        return new EnhancementModal(driver);
    }

    public NewFeatureModal openNewFeatureModal() {
        WebDriver driver = DriverFactory.getDriver();
        WebElement feedbackButton = driver.findElement(By.xpath("//button[contains(.,'Feedback')]"));
        WaitUtils.visible(driver, feedbackButton);
        System.out.println("Feedback button: " + feedbackButton.getText());
        feedbackButton.click();
        WebElement newFeatureBtn = driver.findElement(By.xpath("//button[.//span[contains(.,'New feature')]]"));
        WaitUtils.visible(driver, newFeatureBtn);
        System.out.println("New Feature Text:" + newFeatureBtn.getText());
        newFeatureBtn.click();
        return new NewFeatureModal(DriverFactory.getDriver());
    }

    public boolean isThemeToggleDisplayed() {
        WaitUtils.visible(DriverFactory.getDriver(), themeToggle);
        if (themeToggle != null && themeToggle.isDisplayed()) {
            System.out.println("Theme Toggle Displayed");
            themeToggle.click();
            return true;
        } else {
            System.out.println("Theme Toggle not Displayed");
            return false;
        }

    }

    public boolean verifyUserManagementIsAvailable() {
        if (userManagementIcon != null && userManagementIcon.isDisplayed()) {
            userManagementIcon.click();
            return true;
        } else {
            return false;
        }
    }

    public boolean isLoggedUserDisplayed() {
        if (loggedInUserName != null && loggedInUserName.isDisplayed()) {
            WaitUtils.visible(DriverFactory.getDriver(), loggedInUserName);
            return true;
        } else {
            return false;
        }

    }

    public boolean profileIconDisplayed() {
        if (profileIcon != null && profileIcon.isDisplayed()) {
            WaitUtils.visible(DriverFactory.getDriver(), profileIcon);
            return true;
        } else {
            return false;
        }

    }

    public void openProfileMenu() {
        if (profileIcon != null && profileIcon.isDisplayed()) {
            profileIcon.click();
        }
    }

    public void openAccountMenu() {
        WebDriver driver = DriverFactory.getDriver();
        if (driver.findElements(By.xpath("//*[normalize-space()='Signed in as']")).isEmpty()) {
            new WebDriverWait(driver, Duration.ofSeconds(10))
                .until(ExpectedConditions.elementToBeClickable(ACCOUNT_MENU_BUTTON))
                .click();
        }
        new WebDriverWait(driver, Duration.ofSeconds(10))
                .until(ExpectedConditions.visibilityOfElementLocated(By.xpath("//*[normalize-space()='Signed in as']")));
    }

    public List<String> getAvailableAccounts() {
        openAccountMenu();
        WaitUtils.visible(DriverFactory.getDriver(), accountDropdown);
        return new Select(accountDropdown).getOptions().stream()
                .map(WebElement::getText)
                .map(String::trim)
                .toList();
    }

    public void selectAccount(String accountName) {
        openAccountMenu();
        WaitUtils.visible(DriverFactory.getDriver(), accountDropdown);
        Select select = new Select(accountDropdown);
        for (WebElement option : select.getOptions()) {
            if (option.getText().trim().equalsIgnoreCase(accountName)) {
                select.selectByVisibleText(option.getText().trim());
                String expectedTitle = accountName.equalsIgnoreCase("— My account —")
                        ? "SIT Dashboard"
                        : "Action Center - Investigator View";
                new WebDriverWait(DriverFactory.getDriver(), Duration.ofSeconds(15))
                        .until(currentDriver -> currentDriver.findElement(DASHBOARD_TITLE)
                                .getText().startsWith(expectedTitle));
                return;
            }
        }
        throw new AccountNotFoundException(String.format("Account %s not found in dropdown", accountName));
    }

    public ChangePasswordModal openChangePasswordModal() {
        openAccountMenu();
        WebDriver driver = DriverFactory.getDriver();
        new WebDriverWait(driver, Duration.ofSeconds(10))
                .until(ExpectedConditions.elementToBeClickable(
                        By.xpath("//button[normalize-space()='Change password']")))
                .click();
        return new ChangePasswordModal(driver);
    }

    public void logout() {
        openAccountMenu();
        WebDriver driver = DriverFactory.getDriver();
        new WebDriverWait(driver, Duration.ofSeconds(10))
                .until(ExpectedConditions.elementToBeClickable(By.xpath("//button[normalize-space()='Log out']")))
                .click();
        new WebDriverWait(driver, Duration.ofSeconds(10))
                .until(ExpectedConditions.visibilityOfElementLocated(By.id("username")));
    }

}
