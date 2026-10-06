package com.investigationai.qa.driver;

import com.investigationai.qa.config.ConfigReader;
import org.openqa.selenium.MutableCapabilities;
import org.openqa.selenium.chrome.ChromeOptions;
import org.openqa.selenium.edge.EdgeOptions;
import org.openqa.selenium.firefox.FirefoxOptions;

public final class OptionsFactory {
    private OptionsFactory() {
    }

    public static MutableCapabilities getOptions(String browser, String testName) {
        boolean headless = Boolean.parseBoolean(ConfigReader.get("headless"));
        MutableCapabilities options;
        switch (browser.toLowerCase()) {
            case "firefox" -> {
                FirefoxOptions firefox = new FirefoxOptions();
                if (headless) firefox.addArguments("-headless");
                options = firefox;
            }
            case "edge" -> {
                EdgeOptions edge = new EdgeOptions();
                if (headless) edge.addArguments("--headless=new");
                options = edge;
            }
            case "chrome" -> {
                ChromeOptions chrome = new ChromeOptions();
                if (headless) chrome.addArguments("--headless=new");
                options = chrome;
            }
            default -> throw new IllegalArgumentException("Unsupported browser: " + browser);
        }
        if (ConfigReader.get("execution").equalsIgnoreCase("grid")) {
            options.setCapability("browserVersion", ConfigReader.get("browserVersion"));
            options.setCapability("platformName", ConfigReader.get("platform"));
            options.setCapability("se:name", testName);
        }
        return options;
    }
}