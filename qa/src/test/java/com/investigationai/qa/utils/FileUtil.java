package com.investigationai.qa.utils;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

public class FileUtil {

    private static final String UPLAOD_DIR = System.getProperty("user.dir") + "/uploads";

    public static String createFoldeNotExists() {
        Path path = Paths.get(UPLAOD_DIR);
        try {
            if (Files.exists(path)) {
                Files.createDirectories(path);
            }
        } catch (Exception e) {
            throw new RuntimeException("Unable to create upload directory");
        }

        return UPLAOD_DIR;

    }

    public static File getFile(String fileName) {
        String folder = createFoldeNotExists();
        return new File(folder + File.separator + fileName);
    }

}
