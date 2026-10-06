
package com.investigationai.qa.modal;

import java.io.File;

import org.openqa.selenium.WebElement;

public class FileUpload {

    private final WebElement uploadElement;

    public FileUpload(WebElement uploadElement) {
        this.uploadElement = uploadElement;
    }

    public void upload(String filePath) {

        File file = new File(filePath);
        if (!file.exists() || !file.isFile()) {
            throw new RuntimeException(
                    "File not found: " + file.getAbsolutePath());
        }
        uploadElement.sendKeys(file.getAbsolutePath());
    }
}
