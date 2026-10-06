package com.investigationai.qa.utils;

import org.openqa.selenium.OutputType;
import org.openqa.selenium.TakesScreenshot;
import org.openqa.selenium.WebDriver;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

public final class ScreenshotUtils {
    private static final DateTimeFormatter FILE_TIME = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmssSSS");

    private ScreenshotUtils() {
    }

    public static String capture(WebDriver driver, String testName) {
        if (!(driver instanceof TakesScreenshot screenshotDriver)) {
            return "";
        }

        Path directory = Path.of("target", "screenshots");
        try {
            Files.createDirectories(directory);
            String safeName = testName.replaceAll("[^a-zA-Z0-9._-]", "_");
            Path destination = directory.resolve(safeName + "-" +
                    LocalDateTime.now().format(FILE_TIME) + ".png");
            File source = screenshotDriver.getScreenshotAs(OutputType.FILE);
            Files.copy(source.toPath(), destination);
            return destination.toString();
        } catch (IOException exception) {
            return "";
        }
    }
}