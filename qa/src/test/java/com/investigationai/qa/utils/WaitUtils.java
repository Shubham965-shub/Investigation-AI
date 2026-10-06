package com.investigationai.qa.utils;

import com.investigationai.qa.config.ConfigReader;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

import java.time.Duration;

public final class WaitUtils {
    private WaitUtils() {
    }

    private static final int TIMEOUT=Integer.parseInt(ConfigReader.get("explicitWaitSeconds"));

    public static WebElement visible(WebDriver driver, WebElement element) {
        return new WebDriverWait(driver, Duration.ofSeconds(TIMEOUT)).until(ExpectedConditions.visibilityOf(element));
    }


    public static boolean urlContains(WebDriver driver, String urlPath) {
        return new WebDriverWait(driver, Duration.ofSeconds(TIMEOUT)).until(ExpectedConditions.urlContains(urlPath));
    }


    public static boolean urlNotContains(WebDriver driver, String urlPath) {
        return new WebDriverWait(driver, Duration.ofSeconds(TIMEOUT)).until(ExpectedConditions.not(ExpectedConditions.urlContains(urlPath)));
    }


}
