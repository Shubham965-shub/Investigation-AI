package com.investigationai.qa.driver;

import java.net.URI;
import java.net.URL;
import java.time.Duration;

import org.openqa.selenium.Dimension;
import org.openqa.selenium.MutableCapabilities;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;
import org.openqa.selenium.edge.EdgeDriver;
import org.openqa.selenium.edge.EdgeOptions;
import org.openqa.selenium.firefox.FirefoxDriver;
import org.openqa.selenium.firefox.FirefoxOptions;
import org.openqa.selenium.remote.RemoteWebDriver;

import com.investigationai.qa.config.ConfigReader;

import io.github.bonigarcia.wdm.WebDriverManager;

public final class DriverFactory {

        private static final ThreadLocal<WebDriver> DRIVER = new ThreadLocal<>();

        private DriverFactory() {
                // Utility class
        }

        public static void startDriver() {
                startDriver(Thread.currentThread().getName());
        }

        public static void startDriver(String testName) {

                String browser = getRequiredConfig("browser").toLowerCase();
                String execution = getRequiredConfig("execution").toLowerCase();
                MutableCapabilities capabilities = OptionsFactory.getOptions(browser, testName);
                WebDriver driver;

                switch (execution) {
                        case "grid":
                                driver = createRemoteDriver(capabilities);
                                break;
                        case "local":
                                driver = createLocalDriver(browser, capabilities);
                                break;
                        default:
                                throw new IllegalArgumentException("Unsupported execution mode: " + execution
                                                + ". Supported: local, grid");
                }

                DRIVER.set(driver);
                configureDriver(driver, execution);
        }

        private static WebDriver createLocalDriver(String browser, MutableCapabilities capabilities) {
                return switch (browser) {
                        case "chrome" -> {
                                WebDriverManager.chromedriver().setup();
                                yield new ChromeDriver((ChromeOptions) capabilities);
                        }
                        case "firefox" -> {
                                WebDriverManager.firefoxdriver().setup();
                                yield new FirefoxDriver((FirefoxOptions) capabilities);
                        }
                        case "edge" -> {
                                WebDriverManager.edgedriver().setup();
                                yield new EdgeDriver((EdgeOptions) capabilities);
                        }
                        default ->
                                throw new IllegalArgumentException("Unsupported browser: " + browser);
                };
        }

        private static WebDriver createRemoteDriver(MutableCapabilities capabilities) {
                String gridUrl = getRequiredConfig("gridUrl");
                try {
                        URL remoteUrl = URI.create(gridUrl).toURL();
                        return new RemoteWebDriver(remoteUrl, capabilities);
                } catch (Exception e) {
                        throw new IllegalStateException("Unable to connect to Selenium Grid: " + gridUrl, e);
                }
        }

        private static void configureDriver(WebDriver driver, String execution) {

                driver.manage().timeouts().implicitlyWait(Duration.ZERO);
                driver.manage().timeouts().pageLoadTimeout(Duration.ofSeconds(60));

                driver.manage().timeouts().scriptTimeout(Duration.ofSeconds(30));

                if (execution.equals("grid")) {
                        driver.manage().window().setSize(new Dimension(1920, 1080));
                } else {
                        driver.manage().window().maximize();
                }
        }

        public static WebDriver getDriver() {
                WebDriver driver = DRIVER.get();
                if (driver == null) {
                        throw new IllegalStateException("WebDriver has not been started for thread: "
                                        + Thread.currentThread().getName());
                }
                return driver;
        }

        public static void quitDriver() {
                WebDriver driver = DRIVER.get();
                try {
                        if (driver != null) {
                                driver.quit();
                        }
                } finally {
                        DRIVER.remove();
                }
        }

        private static String getRequiredConfig(String key) {
                String value = ConfigReader.get(key);
                if (value == null || value.isBlank()) {
                        throw new IllegalStateException("Missing required configuration: " + key);
                }

                return value.trim();
        }
}
