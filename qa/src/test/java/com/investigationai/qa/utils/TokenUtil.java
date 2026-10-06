package com.investigationai.qa.utils;

import org.openqa.selenium.JavascriptExecutor;
import org.openqa.selenium.WebDriver;

public class TokenUtil {

    public static String getAccessToken(WebDriver driver) {
        JavascriptExecutor js = (JavascriptExecutor) driver;
        String token = (String) js.executeScript(
                "return localStorage.getItem('auth_token');");

        return token;
    }

    public static String getBearerToken(WebDriver driver) {
        String token = getAccessToken(driver);
        return token == null ? null : "Bearer " + token;
    }
}
