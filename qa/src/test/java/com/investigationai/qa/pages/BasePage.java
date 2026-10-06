package com.investigationai.qa.pages;

import com.investigationai.qa.config.ConfigReader;
import com.investigationai.qa.utils.WaitUtils;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.PageFactory;

public abstract class BasePage {

    protected final WebDriver driver;

    protected BasePage(WebDriver driver) {
        if (driver == null) {
            throw new IllegalArgumentException("WebDriver cannot be null");
        }

        this.driver = driver;
        PageFactory.initElements(driver, this);
    }

    protected void open(String path) {
        if (path == null || path.isBlank()) {
            throw new IllegalArgumentException("Page path cannot be null or empty");
        }

        String baseUrl = ConfigReader.get("baseUrl");

        if (baseUrl == null || baseUrl.isBlank()) {
            throw new IllegalArgumentException("baseUrl is not configured");
        }

        String url = baseUrl.endsWith("/")
                ? baseUrl.substring(0, baseUrl.length() - 1) + path
                : baseUrl + path;

        driver.get(url);
    }

    protected void waitForPageElement(WebElement element) {
        WaitUtils.visible(driver, element);
    }
}
