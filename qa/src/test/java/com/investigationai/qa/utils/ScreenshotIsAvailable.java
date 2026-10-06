package com.investigationai.qa.utils;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import javax.swing.JFileChooser;
import javax.swing.filechooser.FileNameExtensionFilter;

import com.investigationai.qa.modal.FileUpload;


public class ScreenshotIsAvailable {

    private ScreenshotIsAvailable() {
    }

    public static void chooseAndUploadScreenshot(String folderName,FileUpload fileUpload) {
        JFileChooser fileChooser = new JFileChooser();
        fileChooser.setDialogTitle("Select " + folderName + " Screenshot");
        FileNameExtensionFilter filter = new FileNameExtensionFilter(
                "Image Files (*.png,*.jpg,*.jpeg)",
                "png","jpg","jpeg"
        );
        fileChooser.setFileFilter(filter);

        int result = fileChooser.showOpenDialog(null);

        if (result != JFileChooser.APPROVE_OPTION) {
            System.out.println("No screenshot selected.");
            return;
        }

        File selectedFile = fileChooser.getSelectedFile();
        System.out.println("Screenshot Type: " + folderName);
        System.out.println("Selected File: " + selectedFile.getName());
        System.out.println("Original Path: " + selectedFile.getAbsolutePath());

        File baseDirectory = new File(
                System.getProperty("user.dir")
                        + File.separator
                        + "src"
                        + File.separator
                        + "test"
                        + File.separator
                        + "resources"
                        + File.separator
                        + "SelectedScreenshots"
        );

        File destinationDirectory = new File(baseDirectory,folderName);

        if (!destinationDirectory.exists()) {
            boolean created = destinationDirectory.mkdirs();

            if (!created) {
                throw new RuntimeException(
                        "Unable to create screenshot folder: "
                                + destinationDirectory.getAbsolutePath()
                );
            }

            System.out.println(
                    "Created folder: "
                            + destinationDirectory.getAbsolutePath()
            );
        }

        File destinationFile = new File(
                destinationDirectory,
                selectedFile.getName()
        );

        try {
            Files.copy(
                    selectedFile.toPath(),
                    destinationFile.toPath(),
                    StandardCopyOption.REPLACE_EXISTING
            );

            System.out.println(
                    "File copied to: "
                            + destinationFile.getAbsolutePath()
            );

        } catch (IOException e) {
            throw new RuntimeException(
                    "Failed to copy selected screenshot: "
                            + selectedFile.getName(),
                    e
            );
        }

        fileUpload.upload(destinationFile.getAbsolutePath());

        System.out.println("Screenshot uploaded successfully.");
        System.out.println("========================================");
    }
}
